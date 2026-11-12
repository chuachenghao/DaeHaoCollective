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

PROJECT STRUCTURE
source/daehao_collective/manage.py is the Django command entry point.
The daehao_collective/ package contains settings, project URLs, ASGI and WSGI.
The marketplace/ app contains models, forms, views, app URLs and tests.
Templates and static assets use Django's app namespaces. Migrations are under
marketplace/migrations/, with one Django-generated 0001_initial.py migration.
Setup commands are under marketplace/management/commands/.
The ml/ folder contains the CSV dataset, trained joblib artifact and metadata.

STACK AND BEHAVIOUR
Django 5.2.17, SQLite, Django templates, ordinary forms and local CSS.
The staff operations panel is custom-built; Django's default admin is not used.
Only the print action uses a small optional JavaScript enhancement.
Payments and delivery are a Singapore-only demonstration. No real funds move.
Image uploads accept validated JPEG, PNG or WebP content up to 5 MB.
Low stock means 1–5 units; zero units means sold out.

RECOMMENDATIONS
The trained DecisionTreeClassifier follows the course's fit/predict workflow.
It uses saved measurements, preferred styles and product attributes to predict
synthetic relevance classes; class 1 appears before class 0, with stable ties.
Train/test data is synthetic. Results do not establish real-world preference
accuracy, clothing fit or a correct size. Actual metrics are in ml/metadata.json.
Missing/incompatible models use a clearly labelled curated selection.

UML ALIGNMENT
The 16 domain classes match the UML diagram on page 12 of
IS2108 Pair Project-1.pdf:
Account, Admin, Customer, Seller, Category, Style, CustomerStylePreference,
Product, ProductStyle, ProductVariant, Cart, CartItem, Address, Order,
SellerOrder and OrderItem.

Each class has its UML-named primary key (accountID, adminID, customerID,
sellerID, categoryID, styleID, preferenceID, productID, productStyleID,
productVariantID, cartID, cartItemID, addressID, orderID, sellerOrderID,
and orderItemID).

Seller.email follows the diagram's label; the subsequent field table calls it
contact_email. The seller registration form keeps separate account/store emails.
Order uses order_status. SellerOrder uses fulfilment_status, tracking_number
and shipped_at. Reviewers reference Admin profiles linked to Account records.
Foreign keys use ordinary Django attribute names, with UML ID column names.
The initial migration creates the current UML schema directly. Existing records,
password hashes, order amounts and delivery details were preserved when the
migration history was consolidated. The database has no non-UML model fields.
Shipment time is recorded only when a seller portion is actually marked shipped.

Verification: automated tests cover the application, style preview ranking,
catalogue seed preservation and exact UML field sets.
A migration cleanup check verified that all existing database records and schema
were unchanged. New databases use the single initial migration.
UML checks cover all domain attributes, field types, relationships, ID columns
and unique keys, including the join-table combinations.
Every marketplace model contains only its diagram attributes and relationships.
There are no supporting model fields or additional marketplace model classes.
Account stores only accountID, username, password, email and role. Django's
password/session methods are inherited without additional account columns.
Styles are connected through CustomerStylePreference and ProductStyle only.

STRICT UML BEHAVIOUR
Product descriptions contain supplied material, care and sizing information.
Product.image is the only stored product image field.
Seller suspension uses approval_status; product archiving uses Product.is_active.
Customer deactivation and individual variant archiving are unavailable because
the UML has no fields for those states. Variant availability depends on stock.

Order names and variant labels come from their linked catalogue records, rather
than additional text snapshots. The UML's saved prices, quantities, commission
amounts and delivery details remain stored with the purchase.
Checkout review and browser-replay information live in the session; no checkout
token is stored on Order. Replay recovery is limited to the current session.
Taxonomy identity uses names; renaming a category/style may require retraining.

COURSE STYLE AND ASSISTANCE
Function views, ModelForms, ORM operations, ordinary loops and template
inheritance follow the supplied lecture and practical examples. Necessary
standard Django additions cover authentication, validation and transaction-safe
purchase/inventory changes. Not every API is claimed to have appeared in class.
This implementation, tests, synthetic data and supporting content were developed
with OpenAI Codex assistance in this conversation. Keep an accurate assistance
record and review the code with your pair for the required report/code review.

SUBMISSION
Complete the group details and YouTube link above. Prepare your pair's final DOCX
report separately, using your assigned group number as its filename.
The project does not need a ZIP to run; package it only when preparing submission.
Do not submit a virtual environment, caches, credentials or unrelated course files.
