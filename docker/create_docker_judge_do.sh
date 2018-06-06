#!/bin/bash

if [[ $# != 1 ]]; then echo "Usage: $0 name"; exit 1; fi;

instance="$1"
do_token=
do_region=fra1
do_size=s-4vcpu-8gb

docker-machine create --driver digitalocean --digitalocean-access-token=$do_token --digitalocean-region=$do_region \
	--digitalocean-image=ubuntu-14-04-x64 --digitalocean-size=$do_size "$instance"

docker-machine scp -r siodockers-vpn/. "$instance":vpn/
docker-machine scp docker-compose.yml "$instance":
docker-machine ssh "$instance" curl -L https://github.com/docker/compose/releases/download/1.21.2/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
docker-machine ssh "$instance" chmod +x /usr/local/bin/docker-compose
docker-machine ssh "$instance" docker-compose build
docker-machine ssh "$instance" docker-compose up -d
