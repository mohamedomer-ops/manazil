from datetime import datetime, timezone

from flask import request


ENGLISH_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
ARABIC_MONTHS = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)
from app.property_rules import PROPERTY_RULES

PROPERTY_TYPE_NAMES = {key: rule["label"] for key, rule in PROPERTY_RULES.items()}


ARABIC = {
    'What do you want to do with your property?': 'ماذا تريد أن تفعل بعقارك؟',
    'Comment': 'ملاحظة',
    'Comment (optional)': 'ملاحظة (اختياري)',
    'Comment must be 2000 characters or fewer.': 'يجب ألا تتجاوز الملاحظة 2000 حرف.',
    'Completed': 'مكتمل',
    'Current': 'الحالي',
    'Upcoming': 'قادم',
    'Purpose': 'الغرض',
    'Room': 'غرفة',
    'Transaction Details': 'تفاصيل العرض',
    'Rent price': 'قيمة الإيجار',
    'Review & Submit': 'المراجعة والنشر',
    'Property posting progress': 'مراحل إضافة العقار',
    'Please complete the highlighted fields.': 'يرجى إكمال الحقول المحددة.',
    'Check your details before publishing. Use Back or the progress navigation to edit.': 'راجع بياناتك قبل النشر. استخدم السابق أو مراحل النموذج للتعديل.',
    'Leave the date empty if available now.': 'اترك التاريخ فارغاً إذا كان العقار متاحاً الآن.',
    'Enter a valid date.': 'أدخل تاريخاً صحيحاً.',
    'Enter a valid value.': 'أدخل قيمة صحيحة.',
    'JavaScript is unavailable. Complete the applicable fields below and submit; the server will validate your listing.': 'جافاسكريبت غير متاح. أكمل الحقول المناسبة وأرسل النموذج؛ سيتحقق الخادم من بيانات العقار.',
    'Warehouse': 'مخزن', 'Floor': 'الطابق', 'Land use': 'استخدام الأرض',
    'Residential': 'سكني', 'Commercial': 'تجاري', 'Agricultural': 'زراعي',
    'Industrial': 'صناعي', 'Mixed use': 'متعدد الاستخدامات',
    'OR': 'أو',
    'Continue with Google': 'المتابعة باستخدام جوجل',
    'Google account': 'حساب جوجل',
    'Google login': 'تسجيل الدخول بجوجل',
    'Social account': 'حساب اجتماعي',
    'Manazil uses a session cookie to keep you signed in and security tokens to protect forms and Google Sign-In. Verification codes have a limited lifetime and are not stored in plain text.': 'يستخدم منازل ملف تعريف ارتباط للجلسة لإبقائك مسجلاً للدخول، ورموز أمان لحماية النماذج وتسجيل الدخول بجوجل. رموز التحقق محدودة الصلاحية ولا تُخزن كنص واضح.',
    'You can edit your account contact information and manage your property listings. For an account and associated sign-in data deletion request, see our Data Deletion page. We may need to verify that the account is yours before acting on a request.': 'يمكنك تعديل بيانات التواصل في حسابك وإدارة إعلاناتك العقارية. لطلب حذف الحساب وبيانات تسجيل الدخول المرتبطة به، راجع صفحة حذف البيانات. قد نحتاج إلى التحقق من ملكيتك للحساب قبل تنفيذ الطلب.',
    'You can request deletion of your Manazil account and associated sign-in data.': 'يمكنك طلب حذف حسابك في منازل وبيانات تسجيل الدخول المرتبطة به.',
    'Tell us that you want your Manazil account and associated data deleted and provide enough information to identify it, such as the contact name or phone number on your account. Do not send passwords, verification codes, or access tokens.': 'اذكر أنك تريد حذف حسابك في منازل والبيانات المرتبطة به، وقدم معلومات كافية لتحديد الحساب مثل اسم التواصل أو رقم الهاتف. لا ترسل كلمات مرور أو رموز تحقق أو رموز وصول.',
    'We will verify account ownership before deleting account information, linked social identities, saved properties, and stored profile pictures. We will review your property listings and photos as part of the request and explain any information we must retain.': 'سنتحقق من ملكيتك للحساب قبل حذف بياناته وهويات تسجيل الدخول الاجتماعية المرتبطة به والعقارات المحفوظة وصور الملف الشخصي المخزنة. سنراجع إعلاناتك العقارية وصورها ضمن الطلب ونوضح لك أي معلومات يجب الاحتفاظ بها.',
    'Google sign-in was cancelled.': 'تم إلغاء تسجيل الدخول بجوجل.',
    'Google sign-in could not be completed. Please try again.': 'تعذر إكمال تسجيل الدخول بجوجل. يرجى المحاولة مرة أخرى.',
    'For Google login, we receive your Google account ID, verified email address, display name, and profile picture when available. We use the account ID to recognize you. We do not store Google access tokens.': 'لتسجيل الدخول بجوجل، نتلقى معرّف حساب جوجل والبريد الإلكتروني المؤكد واسم العرض وصورة الملف الشخصي عند توفرها. نستخدم معرّف الحساب للتعرف عليك. لا نخزن رموز وصول جوجل.',
    'A deletion request also covers any Google identity and Google profile picture associated with your Manazil account.': 'يشمل طلب الحذف أيضًا أي هوية جوجل أو صورة ملف شخصي من جوجل مرتبطة بحسابك في منازل.',
    'Legal information': 'المعلومات القانونية',
    'Privacy Policy': 'سياسة الخصوصية',
    'Data Deletion': 'حذف البيانات',
    'Information we process': 'المعلومات التي نعالجها',
    'How information is used and shared': 'كيفية استخدام المعلومات ومشاركتها',
    'Sessions and security': 'الجلسات والأمان',
    'Your choices and deletion': 'خياراتك وحذف البيانات',
    'Manazil is a Sudanese property marketplace. This page explains the information used to provide accounts, property listings, and saved properties.': 'منازل سوق سوداني للعقارات. توضح هذه الصفحة المعلومات المستخدمة لتقديم الحسابات وإعلانات العقارات والعقارات المحفوظة.',
    'If you provide them, we store your account contact name, WhatsApp number, and Owner or Broker role. Listings include the property details, photos, price, location, and the contact information you choose for that listing. We also store your saved-property choices.': 'إذا قدمتها، نخزن اسم التواصل في حسابك ورقم واتساب وصفة المالك أو الوسيط. تتضمن الإعلانات تفاصيل العقار وصوره وسعره وموقعه وبيانات التواصل التي تختارها لذلك الإعلان. ونخزن أيضاً العقارات التي تحفظها.',
    'We use this information to sign you in, manage your account and listings, show public property details, and let people contact the listing contact. Public listings may show their photos and listing contact information to visitors.': 'نستخدم هذه المعلومات لتسجيل دخولك وإدارة حسابك وإعلاناتك وعرض تفاصيل العقارات العامة وتمكين الزوار من التواصل مع جهة الاتصال في الإعلان. قد تُعرض صور الإعلان العام ومعلومات التواصل الخاصة به للزوار.',
    'How to request deletion': 'كيفية طلب الحذف',
    'What happens next': 'ماذا يحدث بعد ذلك',
    'Email your request to': 'أرسل طلبك عبر البريد الإلكتروني إلى',
    'Authentication is temporarily unavailable.': 'خدمة تسجيل الدخول غير متاحة مؤقتاً.',
    'Manazil Administration': 'إدارة منازل',
    'Administration navigation': 'التنقل في الإدارة',
    'Admin Login': 'دخول الإدارة',
    'Access denied': 'الوصول مرفوض',
    'This account does not have administrator access.': 'هذا الحساب لا يملك صلاحية الإدارة.',
    'Sign in with your administrator phone number.': 'سجّل الدخول برقم هاتف حساب المسؤول.',
    'Invalid or expired verification code.': 'رمز التحقق غير صحيح أو انتهت صلاحيته.',
    'Dashboard': 'لوحة التحكم', 'Users': 'المستخدمون', 'Reports': 'التقارير',
    'Admin Management': 'إدارة المسؤولين', 'Role': 'الصلاحية',
    'User': 'مستخدم', 'Admin': 'مسؤول', 'Active': 'نشط', 'Suspended': 'موقوف',
    'Account status': 'حالة الحساب', 'Authentication method': 'طريقة تسجيل الدخول',
    'Total Properties': 'إجمالي العقارات', 'Published Properties': 'العقارات المنشورة',
    'Available Properties': 'العقارات المتاحة', 'Rented Properties': 'العقارات المؤجرة',
    'Properties for Rent': 'عقارات للإيجار', 'Properties for Sale': 'عقارات للبيع',
    'Total Registered Users': 'إجمالي المستخدمين', 'Owner listings': 'إعلانات الملاك',
    'Broker listings': 'إعلانات الوسطاء', 'Properties with photos': 'عقارات بصور',
    'Properties without photos': 'عقارات دون صور', 'Recent Properties': 'أحدث العقارات',
    'Recent Users': 'أحدث المستخدمين', 'View all users': 'عرض جميع المستخدمين',
    'Publication Status': 'حالة النشر', 'Moderation': 'الإشراف',
    'Clear': 'سليم', 'Disabled': 'معطّل', 'Disabled by administration': 'معطّل بواسطة الإدارة',
    'Disable Property': 'تعطيل العقار', 'Restore Property': 'إعادة إتاحة العقار',
    'Confirm this property moderation action?': 'هل تؤكد إجراء الإشراف على هذا العقار؟',
    'Suspend User': 'إيقاف المستخدم', 'Reactivate User': 'إعادة تنشيط المستخدم',
    'Confirm this account status change?': 'هل تؤكد تغيير حالة الحساب؟',
    'Current Administrators': 'المسؤولون الحاليون', 'Promote Existing User': 'ترقية مستخدم موجود',
    'Find an existing account in Users, then promote it here by ID.': 'ابحث عن حساب موجود في المستخدمين، ثم رقّه باستخدام رقمه.',
    'User ID': 'رقم المستخدم', 'Grant Admin': 'منح صلاحية المسؤول',
    'Revoke Admin': 'سحب صلاحية المسؤول', 'Confirm revoking admin rights?': 'هل تؤكد سحب صلاحية المسؤول؟',
    'Properties by State': 'العقارات حسب الولاية', 'Rent vs Sale': 'الإيجار والبيع',
    'Available vs Rented': 'المتاح والمؤجر', 'Owner vs Broker': 'المالك والوسيط',
    'New Properties Over Time': 'العقارات الجديدة بمرور الوقت',
    'New Users Over Time': 'المستخدمون الجدد بمرور الوقت',
    'No data yet.': 'لا توجد بيانات بعد.', 'No properties found.': 'لا توجد عقارات.',
    'No users found.': 'لا يوجد مستخدمون.', 'Page': 'الصفحة', 'Pages': 'الصفحات',
    'Price': 'السعر', 'Created': 'تاريخ الإنشاء', 'Updated': 'آخر تحديث',
    'User Details': 'تفاصيل المستخدم', 'Owner account': 'حساب المالك',
    'Property photo': 'صورة العقار', 'Neighborhood': 'الحي',
    'Contact Name': 'اسم جهة التواصل', 'Previous': 'السابق',
    'Yes': 'نعم', 'No': 'لا',
    'bedrooms': 'غرف نوم',
    'bathrooms': 'حمام',
    'Sudan': 'السودان',
    'Find your next home': 'ابحث عن بيتك القادم',
    'Properties for rent and sale across Sudan': 'عقارات للإيجار والبيع في السودان',
    'Search properties': 'البحث عن عقار',
    'Find a property': 'ابحث عن عقار',
    'Rent': 'إيجار',
    'Buy': 'شراء',
    'View all': 'عرض الكل',
    'Post': 'أضف',
    'Post a Property': 'أضف عقاراً',
    'Profile': 'حسابي',
    'Mobile navigation': 'التنقل على الهاتف',
    'Sign in': 'تسجيل الدخول',
    'Search for Property': 'ابحث عن عقار',
    'Search': 'بحث',
    'Explore Manazil': 'استكشف منازل',
    'Find what fits you': 'اعثر على ما يناسبك',
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
    'Cancel': 'إلغاء',
    'Development account': 'حساب تجريبي',
    'Sign in with development account': 'الدخول بالحساب التجريبي',
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
    "Sign In": "تسجيل الدخول",
    "Country calling code": "رمز الاتصال الدولي",
    "Full name": "الاسم الكامل",
    "Password": "كلمة المرور",
    "Confirm password": "تأكيد كلمة المرور",
    "Use a password between 8 and 128 characters.": "استخدم كلمة مرور تتراوح بين 8 و128 حرفاً.",
    "Passwords do not match.": "كلمتا المرور غير متطابقتين.",
    "Invalid phone number or password.": "رقم الهاتف أو كلمة المرور غير صحيحة.",
    "This phone number is already associated with an account.": "رقم الهاتف هذا مرتبط بحساب بالفعل.",
    "Phone OTP login": "تسجيل الدخول برمز الهاتف",
    "Password login": "تسجيل الدخول بكلمة المرور",
    "Continue with code": "المتابعة بالرمز",
    "Don't have an account?": "ليس لديك حساب؟",
    'Login / Sign Up': 'تسجيل الدخول / إنشاء حساب',
    'Sign Up': 'إنشاء حساب',
    'Already have an account?': 'لديك حساب بالفعل؟',
    'New to Manazil?': 'جديد في منازل؟',
    'An account with this number already exists. Please log in.': 'يوجد حساب بهذا الرقم بالفعل. يرجى تسجيل الدخول.',
    'No account with this number. Please sign up.': 'لا يوجد حساب بهذا الرقم. يرجى إنشاء حساب.',

    "Phone Number": "رقم الهاتف", "Verified Phone Number": "رقم الهاتف الموثق",
    "WhatsApp Number": "رقم واتساب", "Account Type": "نوع الحساب",
    "This number will be used for WhatsApp and phone calls.": "سيتم استخدام هذا الرقم للتواصل عبر واتساب أو الاتصال بك.",
    "Contact via WhatsApp": "التواصل عبر واتساب", "Call property contact": "الاتصال بصاحب العقار",
    "Call": "اتصال",
    "Save Changes": "حفظ التغييرات",
    "Account information updated successfully": "تم تحديث معلومات الحساب بنجاح",
    "Login": "تسجيل الدخول", "Phone number": "رقم الهاتف",
    "We'll send a verification code to your WhatsApp.": "سنرسل رمز التحقق إلى واتساب.",
    "Continue": "متابعة", "Verification code": "رمز التحقق",
    "Enter the 6-digit verification code.": "أدخل رمز التحقق المكون من 6 أرقام.",
    "Verify": "تحقق", "Resend code": "إعادة إرسال الرمز",
    "Change phone number": "تغيير رقم الهاتف", "My Account": "حسابي",
    'Complete your profile': 'أكمل ملفك الشخصي',
    'Add your WhatsApp/mobile number for Manazil contact and property listings.': 'أضف رقم واتساب أو هاتفك المحمول للتواصل عبر منازل وبشأن إعلاناتك العقارية.',
    'WhatsApp/mobile number': 'رقم واتساب أو الهاتف المحمول',
    'Save number': 'حفظ الرقم',
    'This number cannot be used for this account.': 'لا يمكن استخدام هذا الرقم لهذا الحساب.',
    'Change your number from the profile completion page.': 'غيّر رقمك من صفحة إكمال الملف الشخصي.',
    'Change WhatsApp/mobile number': 'تغيير رقم واتساب أو الهاتف المحمول',
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
    "WhatsApp": "واتساب",
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


ARABIC.update({
    'Verified account': 'حساب موثق',
    'Property poster': 'ناشر العقار',
    'Enter your property details to publish on Manazil': 'أدخل بيانات عقارك لنشره على منازل',
    'Choose the offer and property type': 'اختر نوع العرض ونوع العقار',
    'Transaction type': 'نوع العرض',
    'Add clear photos of your property': 'أضف صورًا واضحة للعقار',
    'Add property photos': 'أضف صور العقار',
    'Choose photos from your device': 'اختر الصور من جهازك',
    'Upload selected photos': 'رفع الصور المحددة',
    'Enter the basic information about your property': 'أدخل المعلومات الأساسية عن العقار',
    'List the amenities available at your property': 'اذكر المرافق المتوفرة في العقار',
    'Enter one amenity per line': 'أدخل مرفقًا واحدًا في كل سطر',
    'Enter contact details for this listing': 'أدخل بيانات التواصل معك',
    'Set your property location': 'حدد موقع العقار',
    'Property location on map (optional)': 'موقع العقار على الخريطة (اختياري)',
    'Select a location on the map': 'تحديد الموقع على الخريطة',
    'Clear selected map location': 'إزالة الموقع المحدد على الخريطة',
    'Select both latitude and longitude on the map.': 'حدد خط العرض وخط الطول معًا على الخريطة.',
    'Select a valid location on the map.': 'حدد موقعًا صالحًا على الخريطة.',
})


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


def relative_posting_age(timestamp, language=None, now=None):
    """UTC listing age, using whole 30-day months without converting to years."""
    if not isinstance(timestamp, datetime):
        return None
    language = language or current_language()
    now = now or datetime.now(timezone.utc)
    # Older naive timestamps represent UTC, matching the application's storage strategy.
    timestamp = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    seconds = max(0, (now - timestamp).total_seconds())
    if seconds < 60:
        return translate('Just now', language)
    for limit, divisor, unit in ((3600, 60, 'minute'), (86400, 3600, 'hour'),
                                 (604800, 86400, 'day'), (2592000, 604800, 'week'),
                                 (float('inf'), 2592000, 'month')):
        if seconds < limit:
            count = int(seconds // divisor)
            if count == 1:
                pattern = f'1 {unit} ago'
            elif count == 2:
                pattern = f'2 {unit}s ago'
            elif language == 'ar' and count > 10:
                pattern = '{count} ' + unit + ' ago'
            else:
                pattern = '{count} ' + unit + 's ago'
            return translate(pattern, language).format(count=count)


ARABIC.update({
    'Just now': 'الآن',
    '1 minute ago': 'منذ دقيقة', '2 minutes ago': 'منذ دقيقتين',
    '{count} minutes ago': 'منذ {count} دقائق', '{count} minute ago': 'منذ {count} دقيقة',
    '1 hour ago': 'منذ ساعة', '2 hours ago': 'منذ ساعتين',
    '{count} hours ago': 'منذ {count} ساعات', '{count} hour ago': 'منذ {count} ساعة',
    '1 day ago': 'منذ يوم', '2 days ago': 'منذ يومين',
    '{count} days ago': 'منذ {count} أيام', '{count} day ago': 'منذ {count} يوم',
    '1 week ago': 'منذ أسبوع', '2 weeks ago': 'منذ أسبوعين',
    '{count} weeks ago': 'منذ {count} أسابيع', '{count} week ago': 'منذ {count} أسبوع',
    '1 month ago': 'منذ شهر', '2 months ago': 'منذ شهرين',
    '{count} months ago': 'منذ {count} أشهر', '{count} month ago': 'منذ {count} شهر',
})


def property_type_label(value, language):
    return translate(PROPERTY_TYPE_NAMES.get(value, value), language)


ARABIC.update({
    'Manazil Sudan': 'منازل السودان',
    'Why choose Manazil': 'لماذا تختار منازل',
    'Manazil · Sudan': 'منازل · السودان',
    'Homes closer to your life': 'منازل أقرب إلى حياتك',
    'Find a suitable home in Sudan easily and safely.': 'ابحث عن منزل مناسب في السودان بسهولة وأمان',
    'Trusted properties': 'عقارات موثوقة',
    'A secure experience': 'تجربة آمنة',
    'Coverage across Sudan': 'تغطية في مختلف الولايات',
    'Welcome back': 'مرحباً بعودتك',
    'Sign in to continue to Manazil': 'سجّل الدخول للمتابعة إلى منازل',
    'Show password': 'إظهار كلمة المرور',
    'Hide password': 'إخفاء كلمة المرور',
})


def template_language():
    language = current_language()
    return {"language": language, "t": lambda message: translate(message, language)}
