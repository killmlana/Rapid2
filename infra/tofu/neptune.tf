resource "aws_neptune_subnet_group" "main" {
  name       = "${var.project_name}-neptune"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.project_name}-neptune-subnet-group" }
}

resource "aws_neptune_cluster" "main" {
  cluster_identifier                  = "${var.project_name}-neptune"
  engine                              = "neptune"
  engine_version                      = "1.3.1.0"
  vpc_security_group_ids              = [aws_security_group.neptune.id]
  neptune_subnet_group_name           = aws_neptune_subnet_group.main.name
  iam_database_authentication_enabled = true
  skip_final_snapshot                 = var.environment == "dev"
  backup_retention_period             = var.environment == "prod" ? 7 : 1
  apply_immediately                   = true

  tags = { Name = "${var.project_name}-neptune-cluster" }
}

resource "aws_neptune_cluster_instance" "main" {
  count              = 1
  cluster_identifier = aws_neptune_cluster.main.id
  instance_class     = var.neptune_instance_class
  engine             = "neptune"
  apply_immediately  = true

  tags = { Name = "${var.project_name}-neptune-instance-${count.index}" }
}
