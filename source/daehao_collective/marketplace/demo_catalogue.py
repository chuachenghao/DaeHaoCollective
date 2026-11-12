"""Fictional garments with distinct visual styles for the recommendation demo."""

# Collection is deliberately assigned to each garment, independent of a shopper's
# gender. Stable SKU prefixes keep this seed metadata separate from product names.
DEMO_COLLECTIONS = {
    "SN-LIN": "MEN",
    "SN-LLC": "UNISEX",
    "SN-TEE": "UNISEX",
    "SN-OVR": "UNISEX",
    "SN-RIB": "UNISEX",
    "SN-TWL": "MEN",
    "FH-EPT": "MEN",
    "FH-POP": "UNISEX",
    "FH-BLZ": "MEN",
    "FH-MID": "WOMEN",
    "SS-CRD": "UNISEX",
    "SS-DNM": "UNISEX",
    "SS-SWT": "UNISEX",
    "SS-JRS": "WOMEN",
    "SA-CMP": "MEN",
    "SA-SKT": "WOMEN",
    "SA-CHR": "UNISEX",
    "SA-WRP": "WOMEN",
    "FH-FKT": "UNISEX",
    "FH-CWT": "UNISEX",
    "FH-CSJ": "UNISEX",
    "FH-SSD": "WOMEN",
    "SS-WST": "UNISEX",
    "SS-DWS": "UNISEX",
    "SS-CFZ": "UNISEX",
    "SS-EJS": "WOMEN",
    "SN-IUS": "MEN",
    "SN-FCT": "MEN",
    "SN-CPJ": "UNISEX",
    "SN-UAD": "WOMEN",
    "SS-HOH": "UNISEX",
    "SS-DPT": "UNISEX",
    "SS-TVJ": "UNISEX",
    "SS-HZD": "WOMEN",
    "FH-POB": "WOMEN",
    "FH-PTT": "MEN",
    "FH-SEB": "UNISEX",
    "FH-PCD": "WOMEN",
    "SA-CCP": "MEN",
    "SA-BCS": "WOMEN",
    "SA-HHJ": "MEN",
    "SA-FTD": "WOMEN",
}

# seller, name, price, category, style, fallback illustration, SKU, colours,
# photograph, construction details, material, care
ADDITIONAL_PRODUCTS = [
    (
        "form", "Fine-gauge knit top", "62.00", "tops", "minimal", "knit",
        "FH-FKT", ["Cream", "Black"], "minimal-knit-top",
        "A high crew neck, short sleeves and a clean straight hem keep this fine-gauge knit deliberately simple. Wear it tucked into tailored trousers or loose over a straight skirt.",
        "Fine-gauge cotton knit with a smooth, closely knitted surface.",
        "Hand wash cold, reshape while damp and dry flat. Do not tumble dry.",
    ),
    (
        "form", "Clean wide-leg trousers", "96.00", "bottoms", "minimal", "trousers",
        "FH-CWT", ["Black", "Stone"], "minimal-wide-trousers",
        "Wide straight legs, a flat waistband and a concealed closure create an uninterrupted silhouette. Discreet side pockets add practicality without extra trim.",
        "Mid-weight cotton and viscose twill with a soft drape.",
        "Gentle cold wash, hang dry and press inside out on low heat.",
    ),
    (
        "form", "Collarless seam jacket", "148.00", "outerwear", "minimal", "coat",
        "FH-CSJ", ["Stone", "Black"], "minimal-collarless-jacket",
        "A boxy collarless jacket with a hidden front placket, discreet seam pockets and a neatly bound round neckline. The pared-back finish highlights its structured shape.",
        "Structured cotton-linen canvas with a lightweight cotton lining.",
        "Dry clean to preserve the jacket structure. Air between wears.",
    ),
    (
        "form", "Square-neck slip dress", "112.00", "dresses", "minimal", "dress",
        "FH-SSD", ["Black", "Navy"], "minimal-slip-dress",
        "Narrow straps, a square neckline and a straight midi-length silhouette define this understated slip dress. A concealed side zip keeps the finish clean.",
        "Smooth viscose blend with a light woven lining.",
        "Hand wash cold, hang to dry in shade and steam gently.",
    ),
    (
        "still", "Weekend striped tee", "44.00", "tops", "casual", "shirt",
        "SS-WST", ["Navy", "Cream"], "casual-striped-tee",
        "Navy and cream horizontal stripes, a soft crew neckline and easy short sleeves make a relaxed everyday tee. Its straight cut works with denim or drawstring shorts.",
        "Breathable cotton jersey with a ribbed cotton neckline.",
        "Machine wash cold with similar colours, reshape and line dry.",
    ),
    (
        "still", "Drawstring weekend shorts", "52.00", "bottoms", "casual", "trousers",
        "SS-DWS", ["Stone", "Navy"], "casual-drawstring-shorts",
        "Relaxed above-knee shorts with an elastic waistband, a visible drawstring and deep side pockets. Soft fabric and an easy leg shape suit low-key weekend outfits.",
        "Washed cotton twill with a soft handle.",
        "Machine wash cold, line dry and iron on medium heat if needed.",
    ),
    (
        "still", "Cloud fleece zip jacket", "86.00", "outerwear", "casual", "coat",
        "SS-CFZ", ["Cream", "Stone"], "casual-fleece-jacket",
        "A cosy zip-front fleece with a stand collar, dropped shoulders and roomy hand pockets. Soft piled texture and a relaxed hem make it an easy light layer.",
        "Polyester fleece with cotton-blend pocket bags.",
        "Gentle cold wash with the zip closed. Air dry; do not iron the fleece.",
    ),
    (
        "still", "Easy jersey sundress", "74.00", "dresses", "casual", "dress",
        "SS-EJS", ["Olive", "Black"], "casual-jersey-dress",
        "A relaxed midi sundress with broad straps, a scoop neckline and an easy flowing skirt. Soft jersey and simple side pockets make it comfortable for everyday dressing.",
        "Cotton jersey with a small amount of elastane for stretch.",
        "Gentle cold wash, reshape and line dry in shade.",
    ),
    (
        "north", "Indigo utility shirt", "88.00", "tops", "workwear", "shirt",
        "SN-IUS", ["Navy", "Olive"], "workwear-utility-shirt",
        "A durable indigo button shirt with two flap chest pockets, reinforced seams and contrast stitching. A gently curved hem allows it to double as a light overshirt.",
        "Mid-weight cotton denim with a washed finish.",
        "Wash cold separately for the first few washes. Turn inside out and line dry.",
    ),
    (
        "north", "Field cargo trousers", "104.00", "bottoms", "workwear", "trousers",
        "SN-FCT", ["Olive", "Stone"], "workwear-cargo-trousers",
        "Straight-leg utility trousers with large side cargo pockets, reinforced knees and sturdy belt loops. Practical pocket placement and hard-wearing fabric define the workwear silhouette.",
        "Heavy cotton twill with a lightly washed surface.",
        "Machine wash cold with similar colours, line dry and press on medium heat.",
    ),
    (
        "north", "Canvas patch-pocket jacket", "132.00", "outerwear", "workwear", "coat",
        "SN-CPJ", ["Stone", "Olive"], "workwear-chore-jacket",
        "A canvas chore jacket with three generous patch pockets, visible dark buttons and a pointed collar. Reinforced stitching and a straight body reference traditional workshop clothing.",
        "Sturdy cotton canvas with a soft washed finish.",
        "Gentle cold wash, reshape and hang dry. Expect the canvas to soften with wear.",
    ),
    (
        "north", "Utility apron dress", "108.00", "dresses", "workwear", "dress",
        "SN-UAD", ["Navy", "Olive"], "workwear-apron-dress",
        "A midi canvas apron dress with broad cross-back straps, large front utility pockets and a straight skirt. Layer over a tee or shirt for a practical workwear outfit.",
        "Medium-weight cotton canvas with reinforced pocket seams.",
        "Machine wash cold, line dry and iron on medium heat.",
    ),
    (
        "still", "Heavyweight oversized hoodie", "92.00", "tops", "streetwear", "knit",
        "SS-HOH", ["Black", "Stone"], "streetwear-hoodie",
        "An oversized pullover hoodie with dropped shoulders, a deep hood and a kangaroo pocket. Thick ribbed cuffs and a broad hem emphasise the generous streetwear shape.",
        "Heavy cotton-rich brushed fleece with ribbed cotton-blend trims.",
        "Wash cold inside out and dry flat. Do not iron directly over ribbed trims.",
    ),
    (
        "still", "Drawcord parachute trousers", "98.00", "bottoms", "streetwear", "trousers",
        "SS-DPT", ["Black", "Olive"], "streetwear-parachute-trousers",
        "Wide nylon trousers with articulated knees, roomy pockets and adjustable drawcord hems. A gathered waistband and lightweight volume create a technical streetwear silhouette.",
        "Lightweight crinkled nylon with polyester mesh pocket bags.",
        "Gentle cold wash in a laundry bag, hang dry and do not iron.",
    ),
    (
        "still", "Two-tone varsity jacket", "156.00", "outerwear", "streetwear", "coat",
        "SS-TVJ", ["Navy", "Black"], "streetwear-varsity-jacket",
        "A varsity bomber with contrasting cream sleeves, striped rib trims and a snap-button front. A roomy body and clean unbranded finish make the athletic shape the focus.",
        "Wool-blend body, cotton-blend sleeves and a lightweight quilted lining.",
        "Dry clean only. Air between wears and store on a broad hanger.",
    ),
    (
        "still", "Half-zip jersey dress", "90.00", "dresses", "streetwear", "dress",
        "SS-HZD", ["Black", "Navy"], "streetwear-zip-dress",
        "An oversized short-sleeve midi dress with a half-zip stand neckline and oversized utility pockets. Dropped shoulders and a straight jersey body give it a sporty streetwear feel.",
        "Heavy cotton jersey with a metal front zip.",
        "Close the zip, wash cold inside out and line dry in shade.",
    ),
    (
        "form", "Pintuck occasion blouse", "84.00", "tops", "formal", "shirt",
        "FH-POB", ["Cream", "Navy"], "formal-pleated-blouse",
        "Fine vertical front pleats, long sleeves and button cuffs give this blouse a polished finish. A neat collar and softly draped body pair with tailored separates.",
        "Lightweight viscose crepe with a smooth, fluid drape.",
        "Hand wash cold, hang dry and press inside out on a low setting.",
    ),
    (
        "form", "Pressed tailored trousers", "116.00", "bottoms", "formal", "trousers",
        "FH-PTT", ["Black", "Navy"], "formal-tailored-trousers",
        "Sharp front creases, a tailored straight leg and discreet waistband tabs create a formal silhouette. A concealed fastening and clean pocket openings suit occasion dressing.",
        "Wool-blend suiting with a smooth partial lining.",
        "Dry clean only. Steam lightly and hang from the waistband between wears.",
    ),
    (
        "form", "Satin-lapel evening blazer", "188.00", "outerwear", "formal", "coat",
        "FH-SEB", ["Black", "Navy"], "formal-satin-blazer",
        "A single-button evening blazer with satin peak lapels, welt pockets and a shaped waist. The contrast between matte suiting and smooth satin gives a clear occasionwear finish.",
        "Wool-blend suiting with satin lapels and a viscose lining.",
        "Professional dry clean only. Use a garment bag and a shaped hanger for storage.",
    ),
    (
        "form", "Pleated chiffon evening dress", "168.00", "dresses", "formal", "dress",
        "FH-PCD", ["Navy", "Black"], "formal-evening-dress",
        "A sleeveless evening midi dress with a defined waist and a flowing pleated skirt. Delicate layers of chiffon move softly while a smooth lining provides coverage.",
        "Lightweight polyester chiffon over a woven viscose lining.",
        "Professional dry clean. Store hanging and steam gently without flattening the pleats.",
    ),
    (
        "sunday", "Crochet collar polo", "86.00", "tops", "vintage", "knit",
        "SA-CCP", ["Cream", "Olive"], "vintage-crochet-polo",
        "An open-knit crochet polo with a pointed collar, a short button placket and scalloped edges. The textured stitch and compact shape recall relaxed mid-century knitwear.",
        "Cotton crochet knit with a soft open-stitch texture.",
        "Hand wash cold, reshape and dry flat. Avoid hanging while wet.",
    ),
    (
        "sunday", "Button-front corduroy skirt", "92.00", "bottoms", "vintage", "trousers",
        "SA-BCS", ["Stone", "Olive"], "vintage-corduroy-skirt",
        "An A-line midi skirt with a centre button placket, broad patch pockets and visible corduroy texture. Its high waist and gently flared shape reference vintage daywear.",
        "Cotton corduroy with a fine vertical wale.",
        "Wash cold inside out, line dry and press on the reverse to protect the pile.",
    ),
    (
        "sunday", "Herringbone heritage jacket", "154.00", "outerwear", "vintage", "coat",
        "SA-HHJ", ["Olive", "Stone"], "vintage-herringbone-jacket",
        "An olive herringbone jacket with a notched collar, contrasting elbow patches and brown buttons. A softly structured body and textured weave give a heritage-inspired finish.",
        "Wool-blend herringbone tweed with cotton elbow patches and a woven lining.",
        "Professional dry clean only. Brush gently and air after wear.",
    ),
    (
        "sunday", "Floral button tea dress", "122.00", "dresses", "vintage", "dress",
        "SA-FTD", ["Cream", "Olive"], "vintage-floral-dress",
        "A cream midi tea dress scattered with tiny muted olive flowers. Short puff sleeves, a V-neck and covered buttons create a soft vintage shape with a defined waist.",
        "Printed viscose crepe with a lightweight woven lining.",
        "Hand wash cold, hang dry in shade and steam on a low setting.",
    ),
]

RETAIL_SIZE_NOTE = (
    "S, M and L are retailer size labels. Check the garment measurements with the "
    "retailer; style recommendations do not guarantee physical fit or a correct size."
)


def detailed_description(name, store_name, construction, material, care):
    return (
        f"{name} from {store_name}. {construction}\n\n"
        f"Material: {material}\n\nCare: {care}\n\n{RETAIL_SIZE_NOTE}"
    )
