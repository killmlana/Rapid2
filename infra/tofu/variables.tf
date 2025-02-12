variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "project_name" {
  type    = string
  default = "rapid2"
}

# Networking
variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["us-west-2a", "us-west-2b"]
}

# Neptune
variable "neptune_instance_class" {
  type    = string
  default = "db.t3.medium"
}

# ECS - GROBID
variable "grobid_cpu" {
  type    = number
  default = 2048
}

variable "grobid_memory" {
  type    = number
  default = 4096
}

variable "grobid_desired_count" {
  type    = number
  default = 1
}

# ECS - VILA (GPU)
variable "vila_gpu_instance_type" {
  type    = string
  default = "g4dn.xlarge"
}

variable "vila_desired_count" {
  type    = number
  default = 1
}

# OpenSearch
variable "opensearch_instance_type" {
  type    = string
  default = "r6g.large.search"
}

variable "opensearch_volume_size" {
  type    = number
  default = 100
}

# Anna's Archive metadata index
variable "annas_opensearch_instance_type" {
  type    = string
  default = "r6g.large.search"
}

variable "annas_opensearch_volume_size" {
  type    = number
  default = 200
}
