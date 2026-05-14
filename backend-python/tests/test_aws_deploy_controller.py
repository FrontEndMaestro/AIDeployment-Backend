import os
import sys
import unittest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.controllers.aws_deploy_controller import (
    _dedupe_ingress_blocks_in_security_groups,
    _enforce_ssh_key_settings,
    _ensure_compose_host_ports_allowed,
    _validate_ssh_command_output,
)


class TestAWSSecurityGroupPostProcessing(unittest.TestCase):
    def test_compose_port_matching_quoted_app_port_default_is_not_added(self):
        terraform_code = '''
variable "app_port" {
  default = "5000"
}

resource "aws_security_group" "instance_sg" {
  ingress {
    from_port   = var.app_port
    to_port     = var.app_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "main" {
  user_data = <<-EOF
ports:
  - "5000:5000"
EOF
}
'''

        result = _ensure_compose_host_ports_allowed(terraform_code)

        self.assertNotIn('description = "App port 5000"', result)
        self.assertEqual(result.count("from_port   = var.app_port"), 1)

    def test_duplicate_literal_and_variable_ingress_blocks_are_deduped(self):
        terraform_code = '''
variable "app_port" {
  default = 5000
}

resource "aws_security_group" "instance_sg" {
  ingress {
    from_port   = var.app_port
    to_port     = var.app_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "App port 5000"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''

        result = _dedupe_ingress_blocks_in_security_groups(terraform_code)

        self.assertEqual(result.count("ingress {"), 1)
        self.assertIn("from_port   = var.app_port", result)
        self.assertNotIn('description = "App port 5000"', result)


class TestAWSSSHKeyPostProcessing(unittest.TestCase):
    def test_ssh_placeholder_is_replaced_with_configured_key_path(self):
        terraform_code = '''
variable "key_name" {
  default = ""
}

resource "aws_instance" "app_server" {
  key_name = var.key_name
}

output "ssh_command" { value = "ssh -i <your-key.pem> ec2-user@${aws_instance.app_server.public_ip}" }
'''

        result = _enforce_ssh_key_settings(terraform_code)

        self.assertIn('default     = "aws-deployment-devops"', result)
        self.assertIn('variable "ssh_private_key_path"', result)
        self.assertIn('~/.ssh/aws-deployment-devops.pem', result)
        self.assertIn("ssh -i ${var.ssh_private_key_path}", result)
        self.assertNotIn("<your-key.pem>", result)

    def test_ssh_placeholder_in_comment_does_not_fail_validation(self):
        terraform_code = '''
output "ssh_command" {
  value = "ssh -i ${var.ssh_private_key_path} ec2-user@${aws_instance.app_server.public_ip}"
}

# ssh -i <key.pem> ec2-user@<public_ip>
'''

        _validate_ssh_command_output(terraform_code)


if __name__ == "__main__":
    unittest.main()
