# Docker
We use docker-compose for setting up the worker and a VPN connection to the internal network where sioworkersd resides.

The `siodockers-vpn` folder needs to include `resolv.conf` used to configure DNS and `vpn.conf` with your OpenVPN Client configuration.

Built image for oioioi-worker is available on DockerHub under `sio2project/siodockers`. All files required to build it are in the `worker/` subdirectory.

You have to edit `docker-compose.yml` and set a proper Filetracker URL and sioworkersd IP.

To launch a worker locally, run `docker-compose up`.

There are also scripts that allow to create machines (using docker-machine) on DigitalOcean and launch workers there. 
In order to run them you have to adjust configuration in `create_docker_judge_do.sh`.
 - `create_docker_judge_do.sh <name>` 			- Create a droplet and run worker with given name
 - `create_many_dockers.sh [name1] [name2]...` 	- Create droplets with given names
 - `remove_workers.sh [name1] [name2]...`		- Remove workers with given names
