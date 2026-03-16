packer {
  required_plugins {
    hcloud = {
      source  = "github.com/hetznercloud/hcloud"
      version = ">= 1.6.0"
    }
  }
}

source "hcloud" "talos" {
  token       = var.hcloud_token
  location    = var.location
  server_type = var.server_type
  image       = "ubuntu-24.04"
  snapshot_name = var.snapshot_name
  ssh_username  = "root"

  rescue = "linux64"
}

build {
  sources = ["source.hcloud.talos"]

  provisioner "file" {
    source      = var.talos_image_path
    destination = "/tmp/talos.raw.xz"
  }

  provisioner "shell" {
    inline = [
      "xz -d /tmp/talos.raw.xz",
      "dd if=/tmp/talos.raw of=/dev/sda bs=4M status=progress",
      "sync",
    ]
  }
}
