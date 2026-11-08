DaeHao Collective — IS2108 Pair Project

Group number: Pair Project 11
Member 1: Chua Cheng Hao, A0320224Y, chuachenghao@u.nus.edu
Member 2: Ong Seng Ming Daemon, A0320948Y, e1523855@u.nus.edu
Full demo video: 

RUN THE PROJECT (Python 3.12 recommended)
Open a terminal in the folder containing this readme.txt, then run:

cd source/daehao_collective
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver

Windows: use py -m venv venv and venv\Scripts\activate for environment setup.
Open http://127.0.0.1:8000/ in your browser.
Run the remaining commands below from source/daehao_collective/.

DEMO ACCOUNTS
Customer: demo_customer
Approved seller: demo_seller
Administrator: demo_staff (use /operations/login/)
Pending seller: demo_pending
Initial password: WeftDemo2026!

USEFUL COMMANDS
System check: python manage.py check
Tests: python manage.py test
Check migrations: python manage.py makemigrations --check --dry-run
Retrain model: python manage.py train_recommender
Create staff: python manage.py create_staff USERNAME EMAIL
