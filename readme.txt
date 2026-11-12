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

The data is fictional. The initial bag contains three units from two sellers,
totalling SGD 220.00. Reseeding preserves existing edits and changed bags.

STYLE DISCOVERY DEMONSTRATION
The demo catalogue contains 42 public garments: the original 18 mixed-style
pieces plus four distinct garments in each of Minimal, Casual, Workwear,
Streetwear, Formal and Vintage. Every style includes a top, bottom, outer layer
and dress, with materials, construction details and care guidance.

Open /for-you/ and choose Minimal, then Streetwear, to compare the actual saved
decision tree's ranking of the same available catalogue. Style previews use
your saved measurements when supported, otherwise a labelled 172 cm / 65 kg
example. Previewing never changes your saved profile. Sign in as demo_customer
and edit My Preferences to demonstrate recommendations using a saved profile.

Model pick badges and counts come from the model's predicted relevance class.
Shared-style labels describe matching product tags separately. Open "See how
the recommendations change the order" to compare the first three alphabetic
items with the model order, or compare with all clothing. Filters and stock
availability apply before ranking. These synthetic-data predictions support
style discovery; they do not measure physical fit or choose a garment size.

Detailed fictional product images were generated with the built-in image_gen
tool. Project-owned WebP assets and the complete generation prompt set are in
marketplace/static/marketplace/images/catalogue/ (prompts.json). Rerun seed_demo
after pulling assets to add new products and upgrade original seed illustrations.
It preserves custom uploads, existing product edits, stock, preferences and bags.
Body text is 18 px on desktop and 17 px on mobile, with larger navigation,
forms, labels and product titles throughout the storefront and operations panel.

USEFUL COMMANDS
System check: python manage.py check
Tests: python manage.py test
Check migrations: python manage.py makemigrations --check --dry-run
Retrain model: python manage.py train_recommender
Create staff: python manage.py create_staff USERNAME EMAIL
