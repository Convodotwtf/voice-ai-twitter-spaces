from urllib3 import connectionpool, poolmanager

def patch_connection_pools(maxsize=10):
    """
    Overrides the default maxsize parameter for HTTP and HTTPS connection pools.
    """
    class CustomHTTPConnectionPool(connectionpool.HTTPConnectionPool):
        def __init__(self, *args, **kwargs):
            kwargs['maxsize'] = maxsize
            super().__init__(*args, **kwargs)

    class CustomHTTPSConnectionPool(connectionpool.HTTPSConnectionPool):
        def __init__(self, *args, **kwargs):
            kwargs['maxsize'] = maxsize
            super().__init__(*args, **kwargs)

    poolmanager.pool_classes_by_scheme['http'] = CustomHTTPConnectionPool
    poolmanager.pool_classes_by_scheme['https'] = CustomHTTPSConnectionPool