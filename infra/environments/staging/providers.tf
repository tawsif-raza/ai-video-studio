terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local backend for now - deliberate, not an oversight. An S3 backend
  # needs a bucket to exist before this stack can use it (chicken-and-egg
  # for the very first apply), and this task is discovery/planning-adjacent
  # (`terraform plan` only, no apply yet - see README.md). Migrate to an S3
  # backend with native locking (`use_lockfile`, Terraform >= 1.10) once a
  # small bootstrap stack creates that bucket - see infra/README.md.
  # backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
