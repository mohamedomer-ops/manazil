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
    "Mark as Rented": "تم التأجير",
    "Make Available": "إتاحة العقار",
    'My Properties': 'عقاراتي',
    'Edit Property': 'تعديل العقار',
    'Back to My Properties': 'العودة إلى عقاراتي',
    'You have not posted any properties yet.': 'لم تضف أي عقارات بعد.',
    'Property updated successfully.': 'تم تحديث العقار بنجاح.',
    'Existing photos are kept when you save.': 'تبقى الصور الحالية عند حفظ التغييرات.',

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
    "Logout": "تسجيل الخروج", "Verification status": "حالة التحقق",
    "Verified": "تم التحقق", "Unverified": "لم يتم التحقق",
    "Account creation date": "تاريخ إنشاء الحساب",
    "Enter a valid phone number.": "أدخل رقم هاتف صالحًا.",
    "Invalid or expired verification code.": "رمز التحقق غير صالح أو منتهي الصلاحية.",
    "Unable to sign in.": "تعذر تسجيل الدخول.",
    "If the number is valid, a verification code will be sent.": "إذا كان الرقم صالحًا، سيتم إرسال رمز التحقق.",
    "Publish Property": "انشر العقار",
    "Category": "التصنيف", "For Rent": "للإيجار", "For Sale": "للبيع",
    "What are you renting?": "ماذا تعرض؟", "Rooms": "غرف", "Entire Property": "عقار كامل",
    "Are you acting as an agent?": "هل تعمل كوسيط؟", "Yes": "نعم", "No": "لا",
    "Add up to 20 photos": "أضف حتى ٢٠ صورة", "Preview photo": "معاينة الصورة", "Photo": "صورة",
    "Rent period": "مدة الإيجار", "Monthly": "شهري", "Weekly": "أسبوعي",
    "Price": "السعر", "Sale price": "سعر البيع", "Weekly rent": "الإيجار الأسبوعي",
    "Contact Details": "بيانات التواصل", "Name": "الاسم", "Phone number": "رقم الهاتف",
    "Neighborhood": "الحي", "A property can contain at most 20 photos.": "الحد الأقصى ٢٠ صورة للعقار.",
    "Sale listings cannot have a rent period.": "عقارات البيع لا تحتوي على مدة إيجار.",
    "Each category can contain up to 4 photos. Photos are optional.": "يمكن إضافة أربع صور كحد أقصى لكل فئة. الصور اختيارية.",
    "Upload photos": "رفع الصور",
    "Add photos": "إضافة الصور",
    "Primary photo": "الصورة الرئيسية",
    "Set primary": "اجعلها رئيسية",
    "Move earlier": "تقديم الصورة",
    "Move later": "تأخير الصورة",
    "Delete": "حذف",
    "No photos added.": "لم تُضف صور.",
    "No photo available": "لا توجد صورة",
    "Submitted date": "تاريخ الإرسال",
    "Status": "الحالة",
    "Draft": "مسودة",
    "Published": "منشور",
    "photos": "صور",
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
    "A category can contain at most 4 photos.": "يمكن إضافة أربع صور كحد أقصى لكل فئة.",
    "Choose a valid photo.": "اختر صورة صالحة.",
    "Choose a valid photo action.": "اختر إجراء صور صالحاً.",
    "An uploaded photo is missing. Please upload it again.": "إحدى الصور المرفوعة مفقودة. يرجى رفعها مجدداً.",
    "This property has already been submitted.": "أُرسل هذا العقار للمراجعة بالفعل.",
    "Arabic title": "العنوان بالعربية",
    "Arabic description": "الوصف بالعربية",
    "Arabic city": "المدينة بالعربية",
    "Arabic area": "المنطقة بالعربية",
    "Add your property details once in Arabic, then review and save your draft.": "أدخل تفاصيل عقارك مرة واحدة بالعربية، ثم راجعها واحفظ المسودة.",
    "One entry. Seven clear steps.": "إدخال واحد. سبع خطوات واضحة.",
    "Complete the property details and review them before saving.": "أكمل تفاصيل العقار وراجعها قبل الحفظ.",
    "Enter property details": "أدخل تفاصيل العقار",
    "Review and save": "راجع واحفظ",
    "Your Arabic details stay with you when you switch the interface language.": "تبقى بياناتك العربية محفوظة عند تبديل لغة الواجهة.",
    "Price & Availability": "السعر والتوافر",
    "Photos": "الصور",
    "Review": "المراجعة",
    "Step": "الخطوة",
    "of": "من",
    "Next": "التالي",
    "Back": "السابق",
    "Edit": "تعديل",
    "Photos will be added in the next stage.": "ستُضاف الصور في المرحلة القادمة.",
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
    "Available Now": "متاح الآن", "Available From a Date": "متاح من تاريخ محدد",
    "Available from date": "تاريخ بدء التوافر",
    "Choose an availability date.": "اختر تاريخ بدء التوافر.",
    "Choose today or a future date.": "اختر تاريخ اليوم أو تاريخًا في المستقبل.",
    "Enter a valid date.": "أدخل تاريخًا صالحًا.",
    "Required only when the property is available from a specific date.": "مطلوب فقط عند اختيار التوافر من تاريخ محدد.",
    "Skip to content": "انتقل إلى المحتوى",
    "Made for Sudan": "من السودان، للسودان",
    "A clearer start for your property.": "بداية واضحة لعقارك.",
    "Add your property's details in Arabic and English, with everything in one place.": "أضف تفاصيل عقارك بالعربية والإنجليزية، واجمع معلوماته في مكان واحد.",
    "Clear details. Two languages. One property.": "تفاصيل واضحة. لغتان. عقار واحد.",
    "Start with the Arabic details, then add the English translation.": "ابدأ بالبيانات العربية، ثم أضف ترجمتها الإنجليزية.",
    "Arabic details": "البيانات العربية", "English translation": "الترجمة الإنجليزية",
    "Your property's title, description and location.": "عنوان عقارك ووصفه وموقعه.",
    "Add the translation without entering the shared details again.": "أضف الترجمة دون إعادة إدخال التفاصيل المشتركة.",
    "Property information": "معلومات العقار", "Form progress": "خطوات إضافة العقار",
    "Shared details stay with you when you switch languages.": "تظل التفاصيل المشتركة محفوظة في النموذج عند تبديل اللغة.",
    "Complete the English translation, then save your property.": "أكمل الترجمة الإنجليزية، ثم احفظ عقارك.",
    "Save Property": "حفظ العقار", "Connection status": "حالة الاتصال",
    "Manazil": "منازل", "Home": "الرئيسية", "Post Property": "أضف عقارك",
    "Sudan Property Rental Platform": "منصة تأجير العقارات في السودان",
    "Manazil System": "حالة نظام منازل", "API": "واجهة البرمجة", "Database": "قاعدة البيانات",
    "Checking…": "جارٍ التحقق…", "Connected": "متصل", "Unavailable": "غير متاح", "Unknown": "غير معروف",
    "Enable JavaScript to display live connection status.": "فعّل جافاسكريبت لعرض حالة الاتصال المباشرة.",
    "Create a property": "إضافة عقار",
    "New properties are saved as Draft and are not publicly visible.": "تُحفظ العقارات الجديدة كمسودات ولا تظهر للجمهور.",
    "Fields marked * are required.": "الحقول المشار إليها بعلامة * مطلوبة.",
    "Basic Information": "المعلومات الأساسية", "Location": "الموقع", "Property Details": "تفاصيل العقار",
    "Title": "العنوان", "Description": "الوصف", "City": "المدينة", "Area": "المنطقة",
    "Property type": "نوع العقار", "Monthly rent": "الإيجار الشهري", "Currency": "العملة",
    "Bedrooms": "غرف النوم", "Bathrooms": "الحمامات", "Size in square meters": "المساحة بالمتر المربع",
    "Furnished": "مفروش", "Amenities": "المرافق", "Contact Information": "معلومات التواصل",
    "Contact name": "اسم جهة الاتصال", "Phone": "رقم الهاتف", "WhatsApp": "رقم واتساب",
    "Contact role": "صفة جهة الاتصال", "Owner": "مالك", "Broker": "وسيط",
    "Availability": "التوافر", "Availability status": "حالة التوافر", "Available": "متاح", "Rented": "مؤجر",
    "Apartment": "شقة", "House": "منزل", "Villa": "فيلا", "Office": "مكتب", "Shop": "محل", "Land": "أرض",
    "Select an option": "اختر أحد الخيارات", "(optional)": "(اختياري)",
    "Enter one amenity per line, such as Air conditioning, Parking, Kitchen, or Balcony.": "أدخل كل مرفق في سطر مستقل، مثل التكييف أو موقف السيارات أو المطبخ أو الشرفة.",
    "Save as Draft": "حفظ كمسودة", "Next: English": "التالي: English", "Back to Arabic": "العودة إلى العربية",
    "The property was not saved. Please correct the highlighted fields.": "لم يُحفظ العقار. يرجى تصحيح الحقول المحددة.",
    "The property could not be saved. Your entries are still here. Please try again.": "تعذّر حفظ العقار. ما زالت بياناتك موجودة. يرجى المحاولة مرة أخرى.",
    "The form could not be submitted. Refresh the page and try again.": "تعذّر إرسال النموذج. حدّث الصفحة وحاول مرة أخرى.",
    "Property #{id} was saved as Draft. It is not publicly visible.": "حُفظ العقار رقم {id} كمسودة، ولا يظهر للجمهور.",
    "This field is required.": "هذا الحقل مطلوب.",
    "Choose one of the available options.": "اختر أحد الخيارات المتاحة.",
    "Remove the invalid character from this field.": "احذف الرمز غير الصالح من هذا الحقل.",
    "Enter a whole number from 0 to 2147483647.": "أدخل عددًا صحيحًا من 0 إلى 2147483647.",
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
