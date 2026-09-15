locals {
  name = "${var.project_name}-${var.environment}"
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name}-db"
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = "${local.name}-db" })
}

resource "aws_kms_key" "rds" {
  description             = "Storage encryption for ${local.name} RDS instance"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = merge(var.tags, { Name = "${local.name}-rds" })
}

resource "aws_db_instance" "this" {
  identifier     = "${local.name}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = aws_kms_key.rds.arn

  db_name  = var.database_name
  username = var.master_username
  # RDS-managed master password (native feature): Terraform never generates,
  # sees, or stores the raw password in state at all. RDS creates and
  # rotates it in Secrets Manager itself - this IS this module's Secrets
  # Manager integration (docs/aws-production-architecture.md §10), not a
  # separate hand-rolled secret.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false

  multi_az                = var.multi_az
  backup_retention_period = var.backup_retention_days
  backup_window           = "17:00-18:00" # 22:30-23:30 IST, low-traffic window
  maintenance_window      = "sun:18:30-sun:19:30"

  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.name}-db-final"
  copy_tags_to_snapshot     = true

  auto_minor_version_upgrade = true

  tags = merge(var.tags, { Name = "${local.name}-db" })
}
