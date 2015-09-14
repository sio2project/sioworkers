CELERY_QUEUES = {'sioworkers': {'exchange': 'sioworkers',
                                'binding_key': 'sioworkers'}}
CELERY_DEFAULT_QUEUE = 'sioworkers'
CELERY_ACKS_LATE = True
CELERY_SEND_EVENTS = True
CELERY_IMPORTS = ['sio.celery.job']
CELERY_ROUTES = {'sio.celery.job.sioworkers_job': dict(queue='sioworkers')}
