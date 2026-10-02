from flask import request


ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
ARABIC_MONTHS = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)
PROPERTY_TYPE_NAMES = {
    "apartment": "Apartment", "house": "House", "villa": "Villa",
    "office": "Office", "shop": "Shop", "land": "Land",
}


ARABIC = {
    'bedrooms': 'غرف نوم',
    'bathrooms': 'حمام',
    'Sudan': 'السودان',
    'Find your next home': 'ابحث عن بيتك القادم',
    'Properties for rent and sale across Sudan': 'عقارات للإيجار والبيع في السودان',
    'Search properties': 'البحث عن عقار',
    'Search': 'بحث',
    'Explore Manazil': 'استكشف منازل',
    'Find what fits you': 'اعثر على ما يناسبك',
    'Properties for Rent': 'عقارات للإيجار',
    'Properties for Sale': 'عقارات للبيع',
    'Explore homes available to rent.': 'تصفح المنازل المتاحة للإيجار.',
    'Explore properties available to buy.': 'تصفح العقارات المتاحة للبيع.',
    'Discover homes': 'اكتشف العقارات',
    'Latest Properties': 'أحدث العقارات',
    'View all properties': 'عرض جميع العقارات',
    'Have a property?': 'هل لديك عقار؟',
    'List your property on Manazil and make it easier for people to find it.': 'أضف عقارك إلى منازل وساعد الباحثين عن منزل في العثور عليه.',
    'A Sudanese property marketplace': 'سوق سوداني للعقارات',
    'Footer navigation': 'روابط التذييل',
    'Find a property that fits your plans.': 'ابحث عن العقار المناسب لك.',
    'Filters': 'تصفية',
    'Transaction': 'نوع المعاملة',
    'Seller Type': 'نوع المعلن',
    'Any': 'الكل',
    'Apply Filters': 'تطبيق الفلاتر',
    'Clear Filters': 'مسح الفلاتر',
    'Results': 'النتائج',
    'properties found': 'عقار',
    'No properties match your filters.': 'لا توجد عقارات تطابق خيارات البحث.',
    'Manage your account information.': 'إدارة معلومات حسابك.',
    'Profile Information': 'معلومات الحساب',
    'Your contact details help prefill new property listings.': 'تُستخدم بيانات اتصالك لتعبئة إعلانات العقارات الجديدة مسبقاً.',
    'Complete your contact details to continue posting.': 'أكمل بيانات اتصالك لمتابعة إضافة العقار.',
    'Read-only': 'غير قابل للتعديل',
    'Account & Security': 'الحساب والأمان',
    'Phone login': 'الدخول برقم الهاتف',
    'Verified phone number': 'رقم هاتف موثق',
    'Facebook account': 'حساب فيسبوك',
    'Development simulation': 'محاكاة تجريبية',
    'Continue with Facebook': 'المتابعة باستخدام فيسبوك',
    'Cancel': 'إلغاء',
    'Development simulation only. No connection to Facebook.': 'محاكاة للتطوير فقط. لا يوجد اتصال بفيسبوك.',
    'Development Facebook Login': 'دخول فيسبوك التجريبي',
    'This is a simulated identity for local testing, not real Facebook authentication.': 'هذه هوية تجريبية للاختبار المحلي، وليست مصادقة حقيقية من فيسبوك.',
    'Development account': 'حساب تجريبي',
    'Sign in with development account': 'الدخول بالحساب التجريبي',
    'No verified phone number. Property posting currently requires a phone-verified contact profile.': 'لا يوجد رقم هاتف موثق. إضافة العقارات تتطلب حالياً بيانات اتصال برقم هاتف موثق.',
    'Saved Properties': 'العقارات المحفوظة',
    'Save Property': 'حفظ العقار',
    'Saved': 'محفوظ',
    'Remove from Saved': 'إزالة من المحفوظة',
    'No longer available': 'لم يعد متاحاً',
    "You haven't saved any properties yet.": 'لم تقم بحفظ أي عقارات بعد.',
    'Browse Properties': 'تصفح العقارات',

    "Mark as Rented": "تم التأجير",
    "Make Available": "إتاحة العقار",
    'My Properties': 'عقاراتي',
    'Edit Property': 'تعديل العقار',
    'Back to My Properties': 'العودة إلى عقاراتي',
    'You have not posted any properties yet.': 'لم تضف أي عقارات بعد.',
    'Property updated successfully.': 'تم تحديث العقار بنجاح.',

    "Menu": "القائمة",
    "Create Account": "إنشاء حساب",
    "Don't have an account?": "ليس لديك حساب؟",
    'Login / Sign Up': 'تسجيل الدخول / إنشاء حساب',
    'Sign Up': 'إنشاء حساب',
    'Already have an account?': 'لديك حساب بالفعل؟',
    'New to Manazil?': 'جديد في منازل؟',
    'An account with this number already exists. Please log in.': 'يوجد حساب بهذا الرقم بالفعل. يرجى تسجيل الدخول.',
    'No account with this number. Please sign up.': 'لا يوجد حساب بهذا الرقم. يرجى إنشاء حساب.',

    "Phone Number": "رقم الهاتف", "Verified Phone Number": "رقم الهاتف الموثق",
    "WhatsApp Number": "رقم WhatsApp", "Account Type": "نوع الحساب",
    "Save Changes": "حفظ التغييرات",
    "Account information updated successfully": "تم تحديث معلومات الحساب بنجاح",
    "Login": "تسجيل الدخول", "Phone number": "رقم الهاتف",
    "We'll send a verification code to your WhatsApp.": "سنرسل رمز التحقق إلى واتساب.",
    "Continue": "متابعة", "Verification code": "رمز التحقق",
    "Enter the 6-digit verification code.": "أدخل رمز التحقق المكون من 6 أرقام.",
    "Verify": "تحقق", "Resend code": "إعادة إرسال الرمز",
    "Change phone number": "تغيير رقم الهاتف", "My Account": "حسابي",
    "Logout": "تسجيل الخروج",
    "Verified": "تم التحقق",
    "Enter a valid phone number.": "أدخل رقم هاتف صالحًا.",
    "Invalid or expired verification code.": "رمز التحقق غير صالح أو منتهي الصلاحية.",
    "Unable to sign in.": "تعذر تسجيل الدخول.",
    "If the number is valid, a verification code will be sent.": "إذا كان الرقم صالحًا، سيتم إرسال رمز التحقق.",
    "Publish Property": "انشر العقار",
    "Category": "التصنيف", "For Rent": "للإيجار", "For Sale": "للبيع",
    "What are you renting?": "ماذا تعرض؟", "Rooms": "غرف", "Entire Property": "عقار كامل",
    "Are you acting as an agent?": "هل تعمل كوسيط؟", "Yes": "نعم", "No": "لا",
    "Preview photo": "معاينة الصورة", "Photo": "صورة",
    "Rent period": "مدة الإيجار", "Monthly": "شهري", "Weekly": "أسبوعي",
    "Price": "السعر", "Sale price": "سعر البيع", "Weekly rent": "الإيجار الأسبوعي",
    "Contact Details": "بيانات التواصل", "Name": "الاسم", "Phone number": "رقم الهاتف",
    "Neighborhood": "الحي", "A property can contain at most 20 photos.": "الحد الأقصى ٢٠ صورة للعقار.",
    "Sale listings cannot have a rent period.": "عقارات البيع لا تحتوي على مدة إيجار.",
    "Add photos": "إضافة الصور",
    "Primary photo": "الصورة الرئيسية",
    "Set as primary": "تعيين كصورة رئيسية",
    "New photos": "الصور الجديدة",
    "Selected photos": "الصور المحددة",
    "Remove selected photo": "إزالة الصورة المحددة",
    "Move earlier": "تقديم الصورة",
    "Move later": "تأخير الصورة",
    "Delete": "حذف",
    "No photo available": "لا توجد صورة",
    "Draft": "مسودة",
    "Published": "منشور",
    "photos": "صور",
    "Previous photo": "الصورة السابقة",
    "Next photo": "الصورة التالية",
    "Choose a file with a safe filename.": "اختر ملفاً باسم آمن.",
    "Only JPEG, PNG, and WebP images are allowed.": "يُسمح فقط بصور JPEG وPNG وWebP.",
    "The image type does not match its filename.": "نوع الصورة لا يطابق امتداد الملف.",
    "The image file is empty.": "ملف الصورة فارغ.",
    "The image exceeds the 5 MB limit.": "حجم الصورة يتجاوز حد 5 ميغابايت.",
    "The image content is invalid.": "محتوى الصورة غير صالح.",
    "The photo session is invalid or expired.": "انتهت صلاحية جلسة الصور أو أنها غير صالحة.",
    "The photo reference is invalid.": "مرجع الصورة غير صالح.",
    "The photo session could not be read.": "تعذرت قراءة جلسة الصور.",
    "Choose a valid photo category.": "اختر فئة صور صالحة.",
    "Choose at least one photo.": "اختر صورة واحدة على الأقل.",
    "Choose a valid photo.": "اختر صورة صالحة.",
    "Choose a valid photo action.": "اختر إجراء صور صالحاً.",
    "An uploaded photo is missing. Please upload it again.": "إحدى الصور المرفوعة مفقودة. يرجى رفعها مجدداً.",
    "This property has already been submitted.": "أُرسل هذا العقار للمراجعة بالفعل.",
    "Photos": "الصور",
    "of": "من",
    "Next": "التالي",
    "Back": "السابق",
    "Edit": "تعديل",
    "Properties": "العقارات",
    "No properties are currently available.": "لا توجد عقارات متاحة حالياً.",
    "Available from": "متاح من",
    "Unfurnished": "غير مفروش",
    "Furnishing": "التأثيث",
    "Property details": "تفاصيل العقار",
    "Contact Owner": "تواصل مع المالك",
    "Contact Broker": "تواصل مع الوسيط",
    "View Property": "عرض العقار",
    "State": "الولاية",
    "Choose a Sudanese state from the list.": "اختر ولاية سودانية من القائمة.",
    "Available Now": "متاح الآن",
    "Skip to content": "انتقل إلى المحتوى",
    "Save Property": "حفظ العقار",
    "Manazil": "منازل", "Home": "الرئيسية", "Post Property": "أضف عقارك",
    "Sudan Property Rental Platform": "منصة تأجير العقارات في السودان",
    "Create a property": "إضافة عقار",
    "Location": "الموقع", "Property Details": "تفاصيل العقار",
    "Title": "العنوان", "Description": "الوصف",
    "Property type": "نوع العقار", "Monthly rent": "الإيجار الشهري", "Currency": "العملة",
    "Sudanese Pound (SDG)": "الجنيه السوداني (SDG)",
    "US Dollar (USD)": "الدولار الأمريكي (USD)",
    "Choose SDG or USD.": "اختر الجنيه السوداني أو الدولار الأمريكي.",
    "Bedrooms": "غرف النوم", "Bathrooms": "الحمامات", "Size in square meters": "المساحة بالمتر المربع",
    "Furnished": "مفروش", "Amenities": "المرافق", "Contact Information": "معلومات التواصل",
    "Phone": "رقم الهاتف", "WhatsApp": "رقم واتساب",
    "Owner": "مالك", "Broker": "وسيط",
    "Availability": "التوافر", "Available": "متاح", "Rented": "مؤجر",
    "Apartment": "شقة", "House": "منزل", "Villa": "فيلا", "Office": "مكتب", "Shop": "محل", "Land": "أرض",
    "Select an option": "اختر أحد الخيارات",
    "The property was not saved. Please correct the highlighted fields.": "لم يُحفظ العقار. يرجى تصحيح الحقول المحددة.",
    "The property could not be saved. Your entries are still here. Please try again.": "تعذّر حفظ العقار. ما زالت بياناتك موجودة. يرجى المحاولة مرة أخرى.",
    "The form could not be submitted. Refresh the page and try again.": "تعذّر إرسال النموذج. حدّث الصفحة وحاول مرة أخرى.",
    "This field is required.": "هذا الحقل مطلوب.",
    "Choose one of the available options.": "اختر أحد الخيارات المتاحة.",
    "Remove the invalid character from this field.": "احذف الرمز غير الصالح من هذا الحقل.",
    "Enter a valid, finite number of 0 or greater.": "أدخل عددًا صالحًا ومحدودًا يساوي صفرًا أو أكثر.",
    "Choose checked or unchecked.": "حدد خيار مفروش أو أزل تحديده.",
}


def current_language():
    return "en" if request.form.get("_language", request.args.get("lang")) == "en" else "ar"


def translate(message, language):
    return ARABIC.get(message, message) if language == "ar" else message


def availability_label(available_from_date, language, today):
    if available_from_date is None or available_from_date <= today:
        return translate("Available Now", language)
    if language == "ar":
        month = ARABIC_MONTHS[available_from_date.month - 1]
        return f"{translate('Available from', language)} {available_from_date.day} {month} {available_from_date.year}"
    month = ENGLISH_MONTHS[available_from_date.month - 1]
    return f"Available from {month} {available_from_date.day}, {available_from_date.year}"


def format_rent(amount):
    formatted = format(amount, ",f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def property_type_label(value, language):
    return translate(PROPERTY_TYPE_NAMES.get(value, value), language)


def template_language():
    language = current_language()
    return {"language": language, "t": lambda message: translate(message, language)}
