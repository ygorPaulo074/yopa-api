from invoke import task

# Task not working, because of the way the setup.py is designed to be interactive.
@task
def setup(c):
    c.run("python src/tools/setup.py", pty=True)