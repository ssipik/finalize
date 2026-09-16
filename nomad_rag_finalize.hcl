variable "image_repo" {
  type    = string
  default = "getregistry.azurecr.io/rag_finalize"
}
variable "image_tag" {
  type = string
}

# Stage 6 (FINALIZE). Registered by bitbucket-pipelines.yml, started by Airflow after embed:
#   nomad job dispatch -meta run_id=<airflow run_id> rag-finalize-template
# One job per run.
job "rag-finalize-template" {
  datacenters = ["dc1"]
  type        = "batch"

  parameterized {
    # The same Airflow run_id the earlier stages got; finalize gates, deletes and
    # cleans up that run's batches and deletions.
    meta_required = ["run_id"]
  }

  group "finalize" {
    count = 1

    restart {
      attempts = 0
      mode     = "fail"
    }
    # Retries are Airflow's job, not Nomad's.
    reschedule {
      attempts  = 0
      unlimited = false
    }

    task "finalize" {
      driver = "docker"

      config {
        image   = "${var.image_repo}:${var.image_tag}"
        # No volume: finalize only reads/writes Postgres and deletes Qdrant points.
        # Collection and gate threshold come from settings.yaml in the image (rag-config).
        command = "python"
        args    = ["-m", "rag_finalize", "--run-id", "${NOMAD_META_run_id}"]
      }

      vault {}

      # Vault secrets + service addresses from Consul, rendered as env vars (same
      # pattern as rag-postgres.hcl), so the code only ever reads env vars.
      template {
        data        = <<EOT
{{- with secret "kv/data/secret/cluster/rag" }}
{{- $user := .Data.data.POSTGRES_USER }}{{ $pw := .Data.data.POSTGRES_PASSWORD }}
{{- range service "rag-postgres" }}
RAG_PG_DSN=postgresql+psycopg://{{ $user }}:{{ $pw | urlquery }}@{{ .Address }}:{{ .Port }}/rag_ingestion
{{- end }}
{{- end }}
{{- range service "qdrant" }}
RAG_QDRANT_URL=http://{{ .Address }}:{{ .Port }}
{{- end }}
EOT
        destination = "secrets/rag.env"
        env         = true
        # A batch run must not be restarted by a secret rotation mid-run.
        change_mode = "noop"
      }

      # Light: a few SQL statements and filtered Qdrant deletes, no document content.
      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
