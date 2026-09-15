locals {
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

module "networking" {
  source = "../../modules/networking"

  project_name              = var.project_name
  environment               = var.environment
  vpc_cidr                  = var.vpc_cidr
  azs                       = var.azs
  enable_second_nat_gateway = var.enable_second_nat_gateway
  tags                      = local.tags
}

module "security_groups" {
  source = "../../modules/security_groups"

  project_name              = var.project_name
  environment               = var.environment
  vpc_id                    = module.networking.vpc_id
  vpc_endpoints_sg_id       = module.networking.vpc_endpoints_sg_id
  alb_ingress_cidrs         = var.alb_ingress_cidrs
  api_allow_internet_egress = var.api_allow_internet_egress
  tags                      = local.tags
}

module "s3" {
  source = "../../modules/s3"

  project_name  = var.project_name
  environment   = var.environment
  force_destroy = var.s3_force_destroy
  tags          = local.tags
}

module "sqs" {
  source = "../../modules/sqs"

  project_name               = var.project_name
  environment                = var.environment
  visibility_timeout_seconds = var.pipeline_timeout_seconds + 300
  tags                       = local.tags
}

module "secrets" {
  source = "../../modules/secrets"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.tags
}

module "ecr" {
  source = "../../modules/ecr"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.tags
}

module "logging" {
  source = "../../modules/logging"

  project_name       = var.project_name
  environment        = var.environment
  log_retention_days = var.log_retention_days
  alarm_email        = var.alarm_email
  tags               = local.tags
}

module "iam" {
  source = "../../modules/iam"

  project_name                  = var.project_name
  environment                   = var.environment
  ecr_repository_arn            = module.ecr.repository_arn
  s3_bucket_arn                 = module.s3.bucket_arn
  s3_kms_key_arn                = module.s3.kms_key_arn
  sqs_queue_arn                 = module.sqs.queue_arn
  rds_master_secret_arn         = module.rds.master_user_secret_arn
  llm_key_parameter_arns        = module.secrets.llm_key_parameter_arns
  jwt_signing_key_parameter_arn = module.secrets.jwt_signing_key_parameter_arn
  log_group_arns                = [module.logging.api_log_group_arn, module.logging.worker_log_group_arn]
  tags                          = local.tags
}

module "rds" {
  source = "../../modules/rds"

  project_name        = var.project_name
  environment         = var.environment
  vpc_id              = module.networking.vpc_id
  private_subnet_ids  = module.networking.private_subnet_ids
  security_group_id   = module.security_groups.rds_sg_id
  instance_class      = var.db_instance_class
  multi_az            = var.db_multi_az
  deletion_protection = var.db_deletion_protection
  tags                = local.tags
}

module "dns" {
  source = "../../modules/dns"

  domain_name = var.domain_name
  create_zone = var.create_dns_zone
  zone_id     = var.existing_dns_zone_id
  tags        = local.tags
}

module "alb" {
  source = "../../modules/alb"

  project_name        = var.project_name
  environment         = var.environment
  vpc_id              = module.networking.vpc_id
  public_subnet_ids   = module.networking.public_subnet_ids
  security_group_id   = module.security_groups.alb_sg_id
  certificate_arn     = module.dns.certificate_arn
  deletion_protection = var.db_deletion_protection # same "protect prod by default" posture as RDS
  tags                = local.tags
}

# The one resource that would otherwise create a module cycle (dns needs
# alb's DNS name; alb needs dns's certificate_arn) - see modules/dns's
# main.tf comment. Only created once a domain is actually configured.
resource "aws_route53_record" "alb_alias" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = module.dns.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = module.alb.alb_dns_name
    zone_id                = module.alb.alb_zone_id
    evaluate_target_health = true
  }
}

module "ecs_cluster" {
  source = "../../modules/ecs_cluster"

  project_name = var.project_name
  environment  = var.environment
  tags         = local.tags
}

module "ecs_api" {
  source = "../../modules/ecs_api"

  project_name                  = var.project_name
  environment                   = var.environment
  cluster_arn                   = module.ecs_cluster.cluster_arn
  cluster_name                  = module.ecs_cluster.cluster_name
  private_subnet_ids            = module.networking.private_subnet_ids
  security_group_id             = module.security_groups.api_sg_id
  target_group_arn              = module.alb.api_target_group_arn
  execution_role_arn            = module.iam.execution_role_arn
  task_role_arn                 = module.iam.api_task_role_arn
  log_group_name                = module.logging.api_log_group_name
  aws_region                    = var.aws_region
  ecr_repository_url            = module.ecr.repository_url
  image_tag                     = var.image_tag
  cpu                           = var.api_cpu
  memory                        = var.api_memory
  min_capacity                  = var.api_min_capacity
  max_capacity                  = var.api_max_capacity
  cors_origins                  = var.cors_origins
  pipeline_max_concurrency      = var.pipeline_max_concurrency
  pipeline_timeout_seconds      = var.pipeline_timeout_seconds
  s3_bucket_name                = module.s3.bucket_id
  sqs_queue_url                 = module.sqs.queue_url
  db_host                       = module.rds.address
  db_port                       = module.rds.port
  db_name                       = module.rds.database_name
  db_master_secret_arn          = module.rds.master_user_secret_arn
  llm_key_parameter_arns        = module.secrets.llm_key_parameter_arns
  jwt_signing_key_parameter_arn = module.secrets.jwt_signing_key_parameter_arn
  tags                          = local.tags
}

module "ecs_worker" {
  source = "../../modules/ecs_worker"

  project_name             = var.project_name
  environment              = var.environment
  cluster_arn              = module.ecs_cluster.cluster_arn
  cluster_name             = module.ecs_cluster.cluster_name
  private_subnet_ids       = module.networking.private_subnet_ids
  security_group_id        = module.security_groups.worker_sg_id
  execution_role_arn       = module.iam.execution_role_arn
  task_role_arn            = module.iam.worker_task_role_arn
  log_group_name           = module.logging.worker_log_group_name
  aws_region               = var.aws_region
  ecr_repository_url       = module.ecr.repository_url
  image_tag                = var.image_tag
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  max_capacity             = var.worker_max_capacity
  use_fargate_spot         = var.use_fargate_spot_for_worker
  sqs_queue_name           = module.sqs.queue_name
  sqs_queue_url            = module.sqs.queue_url
  pipeline_max_concurrency = var.pipeline_max_concurrency
  pipeline_timeout_seconds = var.pipeline_timeout_seconds
  s3_bucket_name           = module.s3.bucket_id
  db_host                  = module.rds.address
  db_port                  = module.rds.port
  db_name                  = module.rds.database_name
  db_master_secret_arn     = module.rds.master_user_secret_arn
  llm_key_parameter_arns   = module.secrets.llm_key_parameter_arns
  tags                     = local.tags
}

module "alarms" {
  source = "../../modules/alarms"

  project_name                = var.project_name
  environment                 = var.environment
  sns_topic_arn               = module.logging.alerts_topic_arn
  alb_arn_suffix              = module.alb.alb_arn_suffix
  api_target_group_arn_suffix = module.alb.api_target_group_arn_suffix
  sqs_queue_name              = module.sqs.queue_name
  sqs_dlq_name                = module.sqs.dlq_name
  rds_instance_id             = module.rds.instance_id
  ecs_cluster_name            = module.ecs_cluster.cluster_name
  ecs_api_service_name        = module.ecs_api.service_name
  ecs_worker_service_name     = module.ecs_worker.service_name
  tags                        = local.tags
}
