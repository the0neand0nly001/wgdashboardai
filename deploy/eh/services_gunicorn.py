import os
bind = '127.0.0.1:' + ('8787' if os.environ.get('EH_ROLE') == 'gateway' else '8791')
workers = 1
threads = 8
worker_class = 'gthread'
timeout = 90
accesslog = '-'
errorlog = '-'
def post_worker_init(worker):
    if os.environ.get('EH_ROLE') == 'gateway':
        import gateway
        gateway.check_config()
    else:
        import node
        node.start()
