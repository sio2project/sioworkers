# Installation

## Python 2

```
$ pip install -r requirements.txt
$ python setup.py install
```

## Python 3

```
$ pip install -r requirements_py3.txt
$ python setup.py install
```

# Tests

All commands are executed in the main directory.

## All tests

```
$ tox
```

## Twisted (Python 2)

```
$ trial sio.sioworkersd.twisted_t
```

## Twisted (Python 3)
```
$ trial sio/sioworkers/twisted_t
```

# Docker

An official Docker image for sioworkers is available at (TODO: update this when the image location is decided).

```
$ docker run --rm \
  --network=sio2-network \
  --cap-add=ALL \
  --privileged \
  -e "SIOWORKERSD_HOST=oioioi" -e "WORKER_ALLOW_RUN_CPU_EXEC=true" \
  --memory="1152m" \
  --cpus=2.0 \
  <TODO: container tag here>
```

Notes:
* `--privileged` is only needed if Sio2Jail is used for judging submissions (ie. `WORKER_ALLOW_RUN_CPU_EXEC` is set to `true`),
* You can limit the memory/CPUs available to the container how you usually would in the container runtime of your choice,
  the container will determine how many workers it should expose to OIOIOI based on that.
* 128 MiB is reserved for processes in the container other than the submission being judged. That is, if you want
  the maximum memory available to a judged program to be 1024 MiB, limit the container's memory to
  128 MiB + (number of workers) * 1024 MiB.

Equivalent Docker Compose configuration:

```yaml
version: '3.8'

...

worker:
  image: <TODO: container tag here>
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 1152m
  cap_add:
    - ALL
  privileged: true
  environment:
    SIOWORKERSD_HOST: 'web'
    WORKER_ALLOW_RUN_CPU_EXEC: 'true'
```

## Environment variables

The container exposes two environment variables, from which only `SIOWORKERSD_HOST` is required.

* `SIOWORKERSD_HOST` - name of the host on which the `sioworkersd` service is available (usually the same as the main OIOIOI instance)
* `WORKER_ALLOW_RUN_CPU_EXEC` - marks this worker as suitable for judging directly on the CPU (without any isolation like Sio2Jail).
  This is used in some contest types (for instance, ACM style contests), however it isn't needed when running the regular OI style
  contests.
