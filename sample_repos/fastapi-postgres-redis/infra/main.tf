provider "aws" {
  region = "ap-south-1"
}

resource "aws_db_instance" "orders" {
  engine            = "postgres"
  engine_version    = "16.4"
  instance_class    = "db.r7g.large"
  allocated_storage = 400
  multi_az          = true
}

resource "aws_elasticache_cluster" "cache" {
  engine    = "redis"
  node_type = "cache.r7g.large"
}
