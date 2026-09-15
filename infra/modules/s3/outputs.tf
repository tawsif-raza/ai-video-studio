output "bucket_id" {
  value = aws_s3_bucket.media.id
}

output "bucket_arn" {
  value = aws_s3_bucket.media.arn
}

output "kms_key_arn" {
  value = aws_kms_key.media.arn
}
