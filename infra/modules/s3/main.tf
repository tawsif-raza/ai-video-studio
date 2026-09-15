locals {
  name = "${var.project_name}-${var.environment}"
}

# Bucket name must be globally unique - suffix with the account id rather
# than a random string so it's deterministic across `terraform plan` runs.
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "media" {
  bucket        = "${local.name}-media-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.force_destroy

  tags = merge(var.tags, { Name = "${local.name}-media" })
}

# Replaces ACL-based access entirely - the modern, recommended default.
resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Belt-and-braces against "accidental public S3 access" (explicitly called
# out as a review item for this task): blocks every public-access mechanism
# at the bucket level, regardless of what any future bucket policy might
# otherwise allow.
resource "aws_s3_bucket_public_access_block" "media" {
  bucket = aws_s3_bucket.media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_kms_key" "media" {
  description             = "SSE-KMS key for ${local.name} media bucket"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(var.tags, { Name = "${local.name}-media" })
}

resource "aws_kms_alias" "media" {
  name          = "alias/${local.name}-media"
  target_key_id = aws_kms_key.media.key_id
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# Deny any request that isn't over TLS - cheap, standard hardening.
resource "aws_s3_bucket_policy" "media" {
  bucket = aws_s3_bucket.media.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.media.arn,
          "${aws_s3_bucket.media.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      }
    ]
  })
}
