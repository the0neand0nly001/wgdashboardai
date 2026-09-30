import os
bind = os.environ.get('EH_BACKEND_BIND', '127.0.0.1') + ':10086'
workers = 1
threads = 4
worker_class = 'gthread'
accesslog = '-'
errorlog = '-'
def post_worker_init(worker):
    import dashboard
    dashboard.startThreads()
    dashboard.DashboardPlugins.startThreads()
