DaeHao Collective — IS2108 Pair Project

Group number: [your group number]
Group leader: [full name, student number, email, contact number]
Second member: [full name, student number, email, contact number]
Full demo video: [YouTube link]

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

Gender is optional under My Preferences: Woman, Man, Non-binary, or Prefer not
to say. For You starts with womenswear plus unisex for Woman, menswear plus
unisex for Man, and all clothing when gender is unspecified or Non-binary.
Its Clothing selection control lets anyone preview any collection without
changing the saved profile. Collection filtering happens before the existing
style model ranks products; gender does not change the height/weight size model.
The demo contains 10 menswear, 12 womenswear and 20 unisex garments. Sellers
and administrators can edit each garment's collection. Clearing personalisation
also clears gender. Run python manage.py migrate after updating existing copies.

Open /for-you/ and choose Minimal, then Streetwear, to compare the actual saved
decision tree's ranking of the same available catalogue. Style previews use
your saved measurements when supported, otherwise a labelled 172 cm / 65 kg
example. Previewing never changes your saved profile. Sign in as demo_customer
and edit My Preferences to demonstrate recommendations using a saved profile.

Model pick badges and counts come from the model's predicted relevance class.
Shared-style labels describe matching product tags separately. Open "See how
the recommendations change the order" to compare the first three alphabetic
items with the model order, or compare with all clothing. Filters and stock
availability apply before ranking. Style predictions support discovery. The
optional height-and-weight size estimate is separate from the relevance score;
neither establishes physical garment fit.

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
Retrain style and size models: python manage.py train_recommender
Add/retrain size model only: python manage.py train_recommender --size-only
Create staff: python manage.py create_staff USERNAME EMAIL

PROJECT STRUCTURE
source/daehao_collective/manage.py is the Django command entry point.
The daehao_collective/ package contains settings, project URLs, ASGI and WSGI.
The marketplace/ app uses ordinary Django files:
- urls.py connects page addresses to functions in views.py.
- views.py handles requests and uses forms.py to check submitted values.
- models.py stores accounts, products, preferences, bags and orders.
- services.py handles bag changes, checkout, stock and order status updates.
- recommendations.py filters clothing and sorts the style model's predictions.
- sizing.py predicts a size and checks whether the product offers it.
