terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Using local state for initial deployment.
  # To migrate to S3 backend, create the bucket and uncomment:
  # backend "s3" {
  #   bucket         = "rapid2-tfstate"
  #   key            = "infra/terraform.tfstate"
  #   region         = "us-west-2"
  #   dynamodb_table = "rapid2-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "rapid2"
      ManagedBy   = "opentofu"
      Environment = var.environment
    }
  }
}
