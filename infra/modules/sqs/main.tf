locals {
  name = "${var.project_name}-${var.environment}"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days - max, gives the longest possible window to notice and fix a repeatedly-failing job type
  sqs_managed_sse_enabled   = true

  tags = merge(var.tags, { Name = "${local.name}-jobs-dlq" })
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${local.name}-jobs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(var.tags, { Name = "${local.name}-jobs" })
}

# Lets the DLQ's own age/depth be inspected/redriven back to the main queue
# without a separate policy grant per principal - standard SQS redrive-allow
# pairing.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.jobs.arn]
  })
}
