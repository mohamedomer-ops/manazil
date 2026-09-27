from flask import request


ARABIC = {
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
    "Manazil": "منازل", "Home": "الرئيسية", "List Your Property": "أضف عقارك",
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


def template_language():
    language = current_language()
    return {"language": language, "t": lambda message: translate(message, language)}
