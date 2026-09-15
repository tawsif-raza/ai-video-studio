locals {
  name = "${var.project_name}-${var.environment}"
}

# One repository, not two: the API and worker services run the same
# codebase (ai_video_studio/) with a different container command
# (docs/aws-production-architecture.md §9) - one image to build, scan, and
# keep in sync between the two services.
resource "aws_ecr_repository" "app" {
  name                 = "${local.name}-app"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
  }

  tags = merge(var.tags, { Name = "${local.name}-app" })
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the most recent ${var.image_retention_count} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.image_retention_count
        }
        action = { type = "expire" }
      }
    ]
  })
}
