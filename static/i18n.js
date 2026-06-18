/* Dar al Sultan — lightweight, dependency-free i18n engine (Phase 3.5).
 *
 * Design: English source text doubles as the translation key. The engine walks
 * visible text nodes (and placeholder/title attributes) and swaps any string it
 * finds in the active dictionary. Strings NOT present in the dictionary (live
 * data such as names, amounts, dates, branch values) are left untouched, so the
 * dictionary itself acts as the chrome whitelist. <option> text is intentionally
 * skipped so form values stay in English and existing logic keeps working.
 *
 * Scope (Phase 3.5): UI chrome only — menus, sidebar, top bar, buttons, labels,
 * headings, form labels, table headers and basic messages. Numbers, currency
 * (OMR) and date formatting are intentionally left in their current format.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "das_lang";
  var SUPPORTED = ["en", "ar"];
  var RTL = { ar: true };
  var SKIP_TAGS = { SCRIPT: 1, STYLE: 1, OPTION: 1, CANVAS: 1, TEXTAREA: 1, NOSCRIPT: 1 };
  var ATTRS = ["placeholder", "title", "aria-label"];

  // First-pass professional Arabic (GCC / Oman business terminology).
  // Finance and production terms are open to review/correction by the owner.
  var AR = {
    /* Sidebar / brand */
    "CFO & Production": "المدير المالي والإنتاج",
    "Dashboard": "لوحة التحكم",
    "Alerts & Control": "التنبيهات والمراقبة",
    "Orders": "الطلبات",
    "Membership": "العضوية",
    "Production": "الإنتاج",
    "Financials": "الماليات",
    "Sales Record": "سجل المبيعات",
    "Employees": "الموظفون",
    "Payroll & Attendance": "الرواتب والحضور",
    "Budgets & Control": "الميزانيات والمراقبة",
    "Reports": "التقارير",
    "Audit Log": "سجل التدقيق",
    "Users & Roles": "المستخدمون والصلاحيات",
    "Settings": "الإعدادات",
    "● Cloud Demo Connected": "● النسخة التجريبية متصلة",
    "Phase 3.4 · Luxury 3D Analytics": "المرحلة 3.4 · تحليلات ثلاثية الأبعاد فاخرة",
    "Made by": "إعداد",

    /* Cloud demo banner */
    "CLOUD DEMO · SAMPLE DATA · OWNER PRESENTATION VERSION": "نسخة تجريبية سحابية · بيانات نموذجية · نسخة عرض المالك",

    /* Login screen */
    "Business Intelligence": "ذكاء الأعمال",
    "& Production Control": "ومراقبة الإنتاج",
    "A secure cloud-ready CFO management system for finance, workshops, employees and multi-branch performance.":
      "نظام إداري آمن وجاهز للسحابة للمدير المالي يغطي الماليات والورش والموظفين وأداء الفروع المتعددة.",
    "Live Branch Access": "وصول مباشر للفروع",
    "Role Permissions": "صلاحيات الأدوار",
    "Audit Trail": "مسار التدقيق",
    "Mobile Installable": "قابل للتثبيت على الجوال",
    "SECURE ACCESS": "دخول آمن",
    "Welcome back": "مرحبًا بعودتك",
    "Sign in to the {company} management application.": "سجّل الدخول إلى نظام إدارة {company}.",
    "Sign in to the management application.": "سجّل الدخول إلى نظام الإدارة.",
    "Username": "اسم المستخدم",
    "Password": "كلمة المرور",
    "Sign In": "تسجيل الدخول",
    "Cloud demo accounts": "حسابات النسخة التجريبية",

    /* Top bar */
    "Management alerts": "تنبيهات الإدارة",
    "Management Alerts": "تنبيهات الإدارة",
    "No unread alerts": "لا توجد تنبيهات غير مقروءة",
    "Mark all read": "تحديد الكل كمقروء",
    "Open Alerts & Control Center": "فتح مركز التنبيهات والمراقبة",
    "Sign Out": "تسجيل الخروج",

    /* Page titles & subtitles (from app.js navigation meta) */
    "Executive Dashboard": "لوحة التحكم التنفيذية",
    "Company-wide financial and production overview": "نظرة عامة على الأداء المالي والإنتاجي للشركة",
    "Daily management summary, actionable alerts and editable thresholds": "ملخص إداري يومي وتنبيهات قابلة للتنفيذ وحدود قابلة للتعديل",
    "Orders & Delivery": "الطلبات والتسليم",
    "Customer booking, production status and delivery tracking": "حجوزات العملاء وحالة الإنتاج وتتبع التسليم",
    "Membership & CRM": "العضوية وإدارة العملاء",
    "Customer cards, wallet balances, validity and usage": "بطاقات العملاء وأرصدة المحفظة والصلاحية والاستخدام",
    "Production Report": "تقرير الإنتاج",
    "Live employee and workshop production tracking": "تتبع مباشر لإنتاج الموظفين والورشة",
    "Financial Entries": "القيود المالية",
    "Income and expense transaction register": "سجل معاملات الإيرادات والمصروفات",
    "Imported invoice, customer, payment and due details": "تفاصيل الفواتير والعملاء والمدفوعات والمستحقات المستوردة",
    "Production performance by employee": "أداء الإنتاج حسب الموظف",
    "Editable monthly salary and daily attendance control": "تحكم بالرواتب الشهرية والحضور اليومي القابل للتعديل",
    "Editable monthly targets, limits and variance analysis": "أهداف شهرية وحدود وتحليل انحرافات قابلة للتعديل",
    "Report Center": "مركز التقارير",
    "Management exports and database backup": "تصدير تقارير الإدارة والنسخ الاحتياطي لقاعدة البيانات",
    "Every create, edit, delete and login activity": "كل عمليات الإنشاء والتعديل والحذف وتسجيل الدخول",
    "Access control and branch permissions": "التحكم في الوصول وصلاحيات الفروع",
    "Language and application preferences": "تفضيلات اللغة والتطبيق",

    /* Common buttons / actions */
    "Refresh": "تحديث",
    "Refresh Dashboard": "تحديث لوحة التحكم",
    "Refresh Alerts": "تحديث التنبيهات",
    "Apply": "تطبيق",
    "Apply Filter": "تطبيق التصفية",
    "Export CSV": "تصدير CSV",
    "Mark All Read": "تحديد الكل كمقروء",
    "Cancel": "إلغاء",
    "Delete": "حذف",
    "Clear": "مسح",
    "Save": "حفظ",
    "Save Budget": "حفظ الميزانية",
    "Save Order": "حفظ الطلب",
    "Save Customer": "حفظ العميل",
    "Save Card": "حفظ البطاقة",
    "Save Plan": "حفظ الباقة",
    "Save Transaction": "حفظ المعاملة",
    "Save Production": "حفظ الإنتاج",
    "Save Total Ready": "حفظ إجمالي الجاهز",
    "Save Entry": "حفظ القيد",
    "Save Category": "حفظ الفئة",
    "Save Employee": "حفظ الموظف",
    "Save User": "حفظ المستخدم",
    "Save Payroll": "حفظ الراتب",
    "Save Attendance": "حفظ الحضور",
    "Save Alert Settings": "حفظ إعدادات التنبيهات",
    "Save Role & Permissions": "حفظ الدور والصلاحيات",
    "Confirm action": "تأكيد الإجراء",
    "Preview File": "معاينة الملف",
    "Import Sales": "استيراد المبيعات",
    "+ Add Order": "+ إضافة طلب",
    "+ Add Customer": "+ إضافة عميل",
    "+ Issue Card": "+ إصدار بطاقة",
    "Manage Plans": "إدارة الباقات",
    "+ Add Plan": "+ إضافة باقة",
    "+ Add Production": "+ إضافة إنتاج",
    "+ Total Ready Completed": "+ إجمالي الجاهز المكتمل",
    "+ Add Entry": "+ إضافة قيد",
    "⇩ Import Sales File": "⇩ استيراد ملف المبيعات",
    "+ Add Employee": "+ إضافة موظف",
    "+ Add Sales Agent": "+ إضافة مندوب مبيعات",
    "+ Attendance": "+ حضور",
    "+ Add Role": "+ إضافة دور",
    "+ Add User": "+ إضافة مستخدم",
    "Manage Categories": "إدارة الفئات",
    "Copy Previous Month": "نسخ الشهر السابق",
    "Manage Expense Categories": "إدارة فئات المصروفات",
    "Manage Membership Plans": "إدارة باقات العضوية",
    "Export Payroll CSV": "تصدير الرواتب CSV",
    "Export Attendance CSV": "تصدير الحضور CSV",

    /* Generic table headers / labels reused across pages */
    "Date": "التاريخ",
    "Date & Time": "التاريخ والوقت",
    "Day": "اليوم",
    "Branch": "الفرع",
    "Status": "الحالة",
    "Notes": "ملاحظات",
    "Action": "إجراء",
    "Actions": "إجراءات",
    "Entered By": "أدخل بواسطة",
    "Added By": "أضيف بواسطة",
    "Changed By": "غُيّر بواسطة",
    "Imported By": "استورد بواسطة",
    "Type": "النوع",
    "Category": "الفئة",
    "Description": "الوصف",
    "Amount": "المبلغ",
    "Reference": "المرجع",
    "Payment": "الدفع",
    "Payment Method": "طريقة الدفع",
    "Payment Status": "حالة الدفع",
    "Customer": "العميل",
    "Phone": "الهاتف",
    "Employee": "الموظف",
    "Role": "الدور",
    "Designation": "المسمى الوظيفي",
    "Total": "الإجمالي",
    "Paid": "المدفوع",
    "Due": "المستحق",
    "Items": "الأصناف",
    "Month": "الشهر",
    "Plan": "الباقة",
    "Commission": "العمولة",
    "Created": "تاريخ الإنشاء",
    "Full Name": "الاسم الكامل",
    "Invoice": "الفاتورة",
    "File": "الملف",
    "Rows": "الصفوف",
    "New": "جديد",
    "Updated": "محدّث",
    "Unchanged": "دون تغيير",
    "Invalid": "غير صالح",
    "Module": "الوحدة",
    "Record": "السجل",
    "Details": "التفاصيل",
    "User": "المستخدم",
    "Previous": "السابق",
    "Revised": "المعدّل",
    "Reason": "السبب",
    "Warning": "تحذير",
    "Permissions": "الصلاحيات",

    /* Dashboard */
    "EXECUTIVE OVERVIEW": "نظرة تنفيذية",
    "Business Performance": "أداء الأعمال",
    /* Executive Dashboard Home (Phase 3.7) */
    "Good Morning": "صباح الخير",
    "Good Afternoon": "مساء الخير",
    "Good Evening": "مساء الخير",
    "Here is today's business performance snapshot.": "إليك لمحة عن أداء الأعمال اليوم.",
    "Executive Business Snapshot": "لمحة تنفيذية عن الأعمال",
    "Company": "الشركة",
    "Active Branch": "الفرع النشط",
    "Date": "التاريخ",
    "All Branches": "كل الفروع",
    "BUSINESS HEALTH SCORE": "مؤشر صحة الأعمال",
    "Overall Performance Index": "مؤشر الأداء العام",
    "ALERTS CENTER": "مركز التنبيهات",
    "Health": "الصحة",
    "Excellent": "ممتاز",
    "Healthy": "جيد",
    "Stable": "مستقر",
    "Needs Attention": "يحتاج إلى انتباه",
    "Alerts": "التنبيهات",
    "margin": "هامش",
    "pcs": "قطعة",
    "overdue": "متأخرة",
    "On track": "على المسار الصحيح",
    "critical": "حرجة",
    "warnings": "تحذيرات",
    "All clear": "لا توجد مشاكل",
    "Priority Notifications": "التنبيهات ذات الأولوية",
    "Open Alerts & Control": "فتح التنبيهات والمراقبة",
    "Unread": "غير مقروءة",
    "No current alerts.": "لا توجد تنبيهات حالية.",
    "EXECUTIVE QUICK ACTIONS": "إجراءات تنفيذية سريعة",
    "Shortcuts": "اختصارات",
    "Add Order": "إضافة طلب",
    "Open Production": "فتح الإنتاج",
    "Open Financials": "فتح الماليات",
    "Open Reports": "فتح التقارير",
    "Company Settings": "إعدادات الشركة",
    "MONTHLY TREND": "الاتجاه الشهري",
    "Income vs Expenses": "الإيرادات مقابل المصروفات",
    "PROFIT OVERVIEW": "نظرة على الأرباح",
    "Income Conversion": "تحويل الإيرادات",
    "BRANCH MIX": "توزيع الفروع",
    "Revenue Contribution": "مساهمة الإيرادات",
    "ORDER CONTROL": "مراقبة الطلبات",
    "Operational Status": "الحالة التشغيلية",
    "PRODUCTION MOMENTUM": "زخم الإنتاج",
    "Monthly Output Trend": "اتجاه الإنتاج الشهري",
    "MANAGEMENT PULSE": "نبض الإدارة",
    "Executive Highlights": "أبرز النقاط التنفيذية",
    "CFO TABLE": "جدول المدير المالي",
    "Monthly Performance Summary": "ملخص الأداء الشهري",
    "Historical months locked": "الأشهر السابقة مقفلة",
    "Income": "الإيرادات",
    "Expenses": "المصروفات",
    "Net Profit": "صافي الربح",
    "Margin": "هامش الربح",
    "Produced Pcs": "القطع المنتجة",
    "Financial": "مالي",
    "Last completed month": "آخر شهر مكتمل",
    "Current month-to-date": "الشهر الحالي حتى تاريخه",

    /* Alerts */
    "MANAGEMENT CONTROL CENTER": "مركز التحكم الإداري",
    "Notifications & Daily Alerts": "الإشعارات والتنبيهات اليومية",
    "Today": "اليوم",
    "TODAY AT A GLANCE": "اليوم بنظرة سريعة",
    "Daily Management Summary": "الملخص الإداري اليومي",
    "ACTION REQUIRED": "إجراء مطلوب",
    "Current Alerts": "التنبيهات الحالية",
    "EDITABLE RULES": "قواعد قابلة للتعديل",
    "Alert Settings": "إعدادات التنبيهات",
    "Settings Branch": "فرع الإعدادات",
    "Membership expiry warning (days)": "تحذير انتهاء العضوية (أيام)",
    "Low production alert below (%)": "تنبيه انخفاض الإنتاج تحت (%)",
    "Attendance reminder hour (0–23)": "ساعة تذكير الحضور (0–23)",
    "Production reminder hour (0–23)": "ساعة تذكير الإنتاج (0–23)",
    "Payroll reminder from day": "تذكير الرواتب من يوم",
    "Income schedule tolerance (%)": "هامش جدول الإيرادات (%)",

    /* Orders */
    "CUSTOMER ORDER CONTROL": "مراقبة طلبات العملاء",
    "Orders & Delivery Tracking": "تتبع الطلبات والتسليم",
    "STATUS MIX": "توزيع الحالات",
    "Orders by Stage": "الطلبات حسب المرحلة",
    "BRANCH LOAD": "حِمل الفروع",
    "Order Distribution": "توزيع الطلبات",
    "COLLECTION CONTROL": "مراقبة التحصيل",
    "Advance vs Balance": "الدفعة المقدمة مقابل الرصيد",
    "ORDER REGISTER": "سجل الطلبات",
    "Booking to Delivery Status": "حالة الحجز حتى التسليم",
    "Order": "الطلب",
    "Booking": "الحجز",
    "Item / Qty": "الصنف / الكمية",
    "Assigned To": "مُسند إلى",
    "Advance": "الدفعة المقدمة",
    "Balance": "الرصيد",
    "Production workflow": "سير عمل الإنتاج",

    /* Membership */
    "CUSTOMER VALUE MANAGEMENT": "إدارة قيمة العملاء",
    "Membership Cards & CRM": "بطاقات العضوية وإدارة العملاء",
    "PORTFOLIO MIX": "توزيع المحفظة",
    "Cards by Plan": "البطاقات حسب الباقة",
    "WALLET LIABILITY": "التزامات المحفظة",
    "Balance by Plan": "الرصيد حسب الباقة",
    "SALES PERFORMANCE": "أداء المبيعات",
    "Agent Commission": "عمولة المندوب",
    "CARD REGISTER": "سجل البطاقات",
    "Active & Historical Membership Cards": "بطاقات العضوية الحالية والسابقة",
    "Card Number": "رقم البطاقة",
    "Sales Agent": "مندوب المبيعات",
    "Issue": "الإصدار",
    "Expiry": "الانتهاء",
    "Current Balance": "الرصيد الحالي",
    "CUSTOMER DIRECTORY": "دليل العملاء",
    "Customers": "العملاء",
    "Cards": "البطاقات",
    "Active Balance": "الرصيد الفعّال",
    "CARD PRODUCTS": "منتجات البطاقات",
    "Membership Plans": "باقات العضوية",
    "SALES INCENTIVE CONTROL": "مراقبة حوافز المبيعات",
    "Monthly Card-Selling Commission": "عمولة بيع البطاقات الشهرية",
    "Cards Sold": "البطاقات المباعة",
    "Total Card Sales": "إجمالي مبيعات البطاقات",
    "Commission Payable": "العمولة المستحقة",

    /* Production */
    "LIVE WORKSHOP CONTROL": "مراقبة الورشة المباشرة",
    "PRODUCTION STAGES OVERVIEW": "نظرة على مراحل الإنتاج",
    "Workshop Flow & Stage Output": "سير الورشة وإنتاج المراحل",
    "Live Workshop": "ورشة مباشرة",
    "Live": "مباشر",
    "EMPLOYEE PRODUCTIVITY": "إنتاجية الموظفين",
    "Top Output by Employee": "أعلى إنتاج حسب الموظف",
    "ACTIVITY MIX": "توزيع الأنشطة",
    "Production Composition": "تكوين الإنتاج",
    "LEADERBOARD": "لوحة المتصدرين",
    "Top Performers": "أفضل الأداءات",
    "WORKSHOP DAY-END OUTPUT": "إنتاج نهاية يوم الورشة",
    "Total Ready Completed": "إجمالي الجاهز المكتمل",
    "EMPLOYEE TOTALS": "إجماليات الموظفين",
    "Current Production Summary": "ملخص الإنتاج الحالي",
    "DAILY BREAKUP": "التفصيل اليومي",
    "Daily Production Entries": "قيود الإنتاج اليومية",
    "Total Activity": "إجمالي النشاط",
    "Total Pcs Produced": "إجمالي القطع المنتجة",
    "Pcs Done": "القطع المنجزة",
    "Produced": "المنتج",
    "Activity": "النشاط",
    "History": "السجل",
    "OT": "إضافي",

    /* Financials */
    "FINANCIAL CONTROL": "المراقبة المالية",
    "Income & Expense Register": "سجل الإيرادات والمصروفات",
    "EXPENSE COMPOSITION": "تكوين المصروفات",
    "Category Breakdown": "تفصيل الفئات",
    "PAYMENT CHANNELS": "قنوات الدفع",
    "Transaction Mix": "توزيع المعاملات",
    "BRANCH PERFORMANCE": "أداء الفروع",
    "Income by Branch": "الإيرادات حسب الفرع",
    "TRANSACTION REGISTER": "سجل المعاملات",
    "Current Entries": "القيود الحالية",

    /* Sales record (POS) */
    "SALES DATA MANAGEMENT": "إدارة بيانات المبيعات",
    "Sales, Customers & Outstanding Dues": "المبيعات والعملاء والمستحقات",
    "SALES TREND": "اتجاه المبيعات",
    "Daily Invoice Value": "قيمة الفواتير اليومية",
    "PAYMENT HEALTH": "صحة المدفوعات",
    "Paid, Partial & Due": "مدفوع وجزئي ومستحق",
    "CUSTOMER VALUE": "قيمة العميل",
    "Top Customers": "أهم العملاء",
    "SALES REGISTER": "سجل المبيعات",
    "Invoice-Level Sales Detail": "تفاصيل المبيعات على مستوى الفاتورة",
    "IMPORT HISTORY": "سجل الاستيراد",
    "Recent Sales Uploads": "آخر عمليات رفع المبيعات",
    "Branch Mode": "وضع الفرع",
    "Customers Added": "العملاء المضافون",
    "Financial Posting": "الترحيل المالي",
    "Imported At": "وقت الاستيراد",

    /* Employees */
    "WORKFORCE MANAGEMENT": "إدارة القوى العاملة",
    "Employees & Work Categories": "الموظفون وفئات العمل",
    "WORKFORCE OUTPUT": "إنتاج القوى العاملة",
    "Employee Production Ranking": "ترتيب إنتاج الموظفين",
    "BRANCH HEADCOUNT": "عدد موظفي الفرع",
    "Team Distribution": "توزيع الفريق",
    "PERFORMANCE": "الأداء",
    "Top Employees": "أفضل الموظفين",

    /* Payroll & attendance */
    "WORKFORCE FINANCE": "ماليات القوى العاملة",
    "Payroll & Attendance": "الرواتب والحضور",
    "PAYROLL MIX": "توزيع الرواتب",
    "Salary Composition": "تكوين الراتب",
    "ATTENDANCE HEALTH": "صحة الحضور",
    "Monthly Status Mix": "توزيع الحالة الشهري",
    "BRANCH PAYROLL": "رواتب الفروع",
    "Net Salary by Branch": "صافي الراتب حسب الفرع",
    "MONTHLY SALARY REGISTER": "سجل الرواتب الشهري",
    "Editable Payroll": "رواتب قابلة للتعديل",
    "Basic Salary": "الراتب الأساسي",
    "Attendance": "الحضور",
    "Bonus": "المكافأة",
    "OT Amount": "مبلغ الإضافي",
    "Allowance": "البدل",
    "Deductions": "الخصومات",
    "Net Salary": "صافي الراتب",
    "DAILY ATTENDANCE": "الحضور اليومي",
    "Attendance Register": "سجل الحضور",
    "Editable payroll workflow": "سير عمل الرواتب القابل للتعديل",

    /* Budgets */
    "CFO PLANNING & CONTROL": "تخطيط ومراقبة المدير المالي",
    "Budgets, Limits & Variance": "الميزانيات والحدود والانحرافات",
    "Not Created": "غير منشأة",
    "BUDGET VS ACTUAL": "الميزانية مقابل الفعلي",
    "Category Variance": "انحراف الفئات",
    "UTILIZATION": "الاستخدام",
    "Expense Budget Used": "المصروف المستخدم من الميزانية",
    "BRANCH PROFITABILITY": "ربحية الفروع",
    "Profit by Branch": "الربح حسب الفرع",
    "INCOME TARGETS": "أهداف الإيرادات",
    "Editable Monthly Targets": "أهداف شهرية قابلة للتعديل",
    "FORECAST": "التوقعات",
    "Month-End Projection": "توقعات نهاية الشهر",
    "EXPENSE LIMITS": "حدود المصروفات",
    "Editable Category Budget vs Actual": "ميزانية الفئة الفعلية القابلة للتعديل",
    "Expense Category": "فئة المصروف",
    "Monthly Budget": "الميزانية الشهرية",
    "Actual": "الفعلي",
    "Remaining": "المتبقي",
    "Used": "المستخدم",
    "Warning At": "تحذير عند",
    "Budget & Actual by Branch": "الميزانية والفعلي حسب الفرع",
    "Income Target": "هدف الإيرادات",
    "Actual Income": "الإيرادات الفعلية",
    "Expense Budget": "ميزانية المصروفات",
    "Actual Expense": "المصروفات الفعلية",
    "Profit": "الربح",
    "APPROVAL CONTROL": "مراقبة الاعتماد",
    "Budget Status": "حالة الميزانية",
    "Unlock / Draft": "إلغاء القفل / مسودة",
    "Approve": "اعتماد",
    "Approve & Lock": "اعتماد وقفل",
    "Close Month": "إغلاق الشهر",
    "REVISION HISTORY": "سجل المراجعات",
    "Budget Changes & Reasons": "تغييرات الميزانية وأسبابها",

    /* Reports */
    "MANAGEMENT REPORTS": "تقارير الإدارة",
    "Report & Backup Center": "مركز التقارير والنسخ الاحتياطي",
    "Production Entries": "قيود الإنتاج",
    "Customer Orders": "طلبات العملاء",
    "Membership Cards": "بطاقات العضوية",
    "Budget vs Actual": "الميزانية مقابل الفعلي",
    "Monthly Payroll": "الرواتب الشهرية",
    "Sales Agent Commission": "عمولة مندوب المبيعات",
    "Database Backup": "نسخ احتياطي لقاعدة البيانات",
    "Print Dashboard": "طباعة لوحة التحكم",
    "Data protection workflow": "سير عمل حماية البيانات",

    /* Audit */
    "INTERNAL CONTROL": "الرقابة الداخلية",

    /* Users & roles */
    "ACCESS CONTROL": "التحكم في الوصول",
    "Users & Permissions": "المستخدمون والصلاحيات",
    "USER ACCOUNTS": "حسابات المستخدمين",
    "Users": "المستخدمون",
    "EDITABLE ACCESS MATRIX": "مصفوفة الوصول القابلة للتعديل",
    "Roles & Permission Sets": "الأدوار ومجموعات الصلاحيات",

    /* Settings page (new) */
    "APPLICATION PREFERENCES": "تفضيلات التطبيق",
    "Language & Region": "اللغة والمنطقة",
    "INTERFACE LANGUAGE": "لغة الواجهة",
    "Your Language": "لغتك",
    "Choose the language for your own account. The change applies immediately.": "اختر لغة حسابك. يُطبّق التغيير فورًا.",
    "COMPANY DEFAULT": "الافتراضي للشركة",
    "Company Default Language": "اللغة الافتراضية للشركة",
    "New users and the sign-in screen use this language until a user chooses their own.": "يستخدم المستخدمون الجدد وشاشة تسجيل الدخول هذه اللغة حتى يختار المستخدم لغته.",
    "Save Company Default": "حفظ الافتراضي للشركة",
    "Interface Language": "لغة الواجهة",
    "English": "الإنجليزية",
    "Arabic": "العربية",

    /* Common form labels in modals */
    "Order Number": "رقم الطلب",
    "Booking Date": "تاريخ الحجز",
    "Due / Delivery Date": "تاريخ الاستحقاق / التسليم",
    "Customer Name": "اسم العميل",
    "Phone Number": "رقم الهاتف",
    "Item Type": "نوع الصنف",
    "Quantity": "الكمية",
    "Assigned Employee": "الموظف المُسند",
    "Email": "البريد الإلكتروني",
    "Address": "العنوان",
    "Card Plan": "باقة البطاقة",
    "Issue Date": "تاريخ الإصدار",
    "Expiry Date": "تاريخ الانتهاء",
    "Transaction Type": "نوع المعاملة",
    "Available Balance": "الرصيد المتاح",
    "Plan Name": "اسم الباقة",
    "Free Deliveries": "عمليات التوصيل المجانية",
    "Overtime Hours": "ساعات العمل الإضافي",
    "Category Name": "اسم الفئة",
    "Employee Name": "اسم الموظف",
    "Daily Target": "الهدف اليومي",
    "Monthly Target": "الهدف الشهري",

    /* KPI card labels (rendered dynamically by app.js) */
    "Current MTD Income": "إيرادات الشهر حتى تاريخه",
    "Current MTD Expenses": "مصروفات الشهر حتى تاريخه",
    "Current Net Profit": "صافي الربح الحالي",
    "Current Produced Pcs": "القطع المنتجة الحالية",
    "Pending Orders": "الطلبات المعلّقة",
    "Ready Orders": "الطلبات الجاهزة",
    "Overdue Orders": "الطلبات المتأخرة",
    "Delivered Orders": "الطلبات المُسلّمة",
    "Active Cards": "البطاقات الفعّالة",
    "Card Wallet Liability": "التزام محافظ البطاقات",
    "Unread Alerts": "التنبيهات غير المقروءة",
    "Critical": "حرجة",
    "Warnings": "تحذيرات",
    "Total Active": "إجمالي الفعّال",
    "Total Orders": "إجمالي الطلبات",
    "Pending": "معلّق",
    "Ready": "جاهز",
    "Overdue": "متأخر",
    "Wallet Outstanding": "رصيد المحفظة المستحق",
    "Expiring Soon": "ينتهي قريبًا",
    "Total Commission": "إجمالي العمولة",
    "Sales Agents": "مندوبو المبيعات",
    "Card Sales": "مبيعات البطاقات",
    "Total Activity Qty": "إجمالي كمية النشاط",
    "Total Stage Pcs Produced": "إجمالي القطع المنتجة بالمراحل",
    "Net Position": "الصافي",
    "Transactions": "المعاملات",
    "Total Sales": "إجمالي المبيعات",
    "Total Paid": "إجمالي المدفوع",
    "Outstanding Due": "المستحق غير المسدد",
    "Invoices": "الفواتير",
    "Total Items": "إجمالي الأصناف",
    "Commission + Bonus": "العمولة + المكافأة",
    "Net Payroll": "صافي الرواتب",
    "Actual Expenses": "المصروفات الفعلية",
    "Remaining Budget": "الميزانية المتبقية",
    "Income Achievement": "تحقيق الإيرادات",
    "Actual Profit": "الربح الفعلي",
    "Projected Profit": "الربح المتوقع",
    "Required Daily Income": "الإيراد اليومي المطلوب",

    /* Company Profile & Owner Settings (Phase 3.6) */
    "Preferences": "التفضيلات",
    "Company Profile": "ملف الشركة",
    "Owner Settings": "إعدادات المالك",
    "COMPANY IDENTITY": "هوية الشركة",
    "These details and the logo brand the dashboard. Future clients can re-brand here without any code change.": "تُستخدم هذه التفاصيل والشعار في هوية اللوحة. يمكن للعملاء مستقبلًا تغيير الهوية من هنا دون أي تعديل برمجي.",
    "Company Name": "اسم الشركة",
    "VAT Number": "الرقم الضريبي",
    "Email Address": "البريد الإلكتروني",
    "Website": "الموقع الإلكتروني",
    "Used on the dashboard header and sign-in screen.": "يظهر في ترويسة اللوحة وشاشة تسجيل الدخول.",
    "Company Address": "عنوان الشركة",
    "Company Logo": "شعار الشركة",
    "PNG, JPG, WEBP or SVG, up to 2 MB.": "PNG أو JPG أو WEBP أو SVG، بحد أقصى 2 ميجابايت.",
    "No logo uploaded": "لم يتم رفع شعار",
    "Company Dashboard": "لوحة تحكم الشركة",
    "Save Company Profile": "حفظ ملف الشركة",
    "LANGUAGE": "اللغة",
    "BRANCH MANAGEMENT": "إدارة الفروع",
    "Branches": "الفروع",
    "Branch name": "اسم الفرع",
    "Add Branch": "إضافة فرع",
    "Save Branch": "حفظ الفرع",
    "EMPLOYEE MANAGEMENT": "إدارة الموظفين",
    "Edit details and assign branch.": "تعديل التفاصيل وتعيين الفرع.",
    "TARGETS MANAGEMENT": "إدارة الأهداف",
    "Company Targets": "أهداف الشركة",
    "Company-level monthly targets for owner reference. Branch and category budgets remain in the Budgets module.": "أهداف شهرية على مستوى الشركة لمرجع المالك. تبقى ميزانيات الفروع والفئات في وحدة الميزانيات.",
    "Monthly Production Target (pcs)": "هدف الإنتاج الشهري (قطعة)",
    "Monthly Income Target (OMR)": "هدف الإيراد الشهري (ر.ع)",
    "Save Targets": "حفظ الأهداف",
    "EMPLOYEE TARGETS": "أهداف الموظفين",
    "Per-Employee Targets": "أهداف كل موظف",
    "Edit": "تعديل",
    "Edit Targets": "تعديل الأهداف",
    "Disable": "تعطيل",
    "Enable": "تفعيل",
    "Active": "فعّال",
    "Inactive": "غير نشط",
    "Disabled": "معطّل"
  };

  var DICTS = { en: {}, ar: AR };

  var lang = "en";
  var origText = new WeakMap();   // Text node -> original (English) string
  var origAttr = new WeakMap();   // Element -> { attr: originalValue }
  var changeHandlers = [];
  var observer = null;
  var applying = false;
  var rafPending = false;

  function dict() { return DICTS[lang] || {}; }
  function isSupported(code) { return SUPPORTED.indexOf(code) !== -1; }

  // Public translate helper for any dynamic string built in JS.
  function t(key, fallback) {
    if (key == null) return "";
    var k = String(key);
    var d = dict();
    if (Object.prototype.hasOwnProperty.call(d, k)) return d[k];
    return fallback != null ? fallback : k;
  }

  function splitWhitespace(value) {
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(value);
    return { lead: m[1], core: m[2], trail: m[3] };
  }

  function translateTextNode(node) {
    var original = origText.get(node);
    if (original === undefined) {
      original = node.nodeValue;
      origText.set(node, original);
    }
    if (lang === "en") {
      if (node.nodeValue !== original) node.nodeValue = original;
      return;
    }
    var parts = splitWhitespace(original);
    if (!parts.core) return;
    var d = dict();
    if (Object.prototype.hasOwnProperty.call(d, parts.core)) {
      var next = parts.lead + d[parts.core] + parts.trail;
      if (node.nodeValue !== next) node.nodeValue = next;
    } else if (node.nodeValue !== original) {
      node.nodeValue = original;
    }
  }

  function translateAttrs(el) {
    for (var i = 0; i < ATTRS.length; i++) {
      var attr = ATTRS[i];
      if (!el.hasAttribute(attr)) continue;
      var store = origAttr.get(el);
      if (!store) { store = {}; origAttr.set(el, store); }
      if (store[attr] === undefined) store[attr] = el.getAttribute(attr);
      var original = store[attr];
      if (lang === "en") {
        if (el.getAttribute(attr) !== original) el.setAttribute(attr, original);
        continue;
      }
      var parts = splitWhitespace(original || "");
      var d = dict();
      if (parts.core && Object.prototype.hasOwnProperty.call(d, parts.core)) {
        el.setAttribute(attr, parts.lead + d[parts.core] + parts.trail);
      } else if (el.getAttribute(attr) !== original) {
        el.setAttribute(attr, original);
      }
    }
  }

  function shouldSkipElement(el) {
    if (!el || el.nodeType !== 1) return false;
    if (SKIP_TAGS[el.tagName]) return true;
    if (el.hasAttribute && el.hasAttribute("data-no-i18n")) return true;
    return false;
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { translateTextNode(root); return; }
    if (root.nodeType !== 1) return;
    if (shouldSkipElement(root)) return;
    if (root.nodeType === 1) translateAttrs(root);
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (node.nodeType === 3) {
          return node.nodeValue && /\S/.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
        return shouldSkipElement(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_SKIP;
      }
    });
    var n;
    while ((n = walker.nextNode())) translateTextNode(n);
    // Attribute pass for descendant elements.
    var attrTargets = root.querySelectorAll ? root.querySelectorAll("[placeholder],[title],[aria-label]") : [];
    for (var i = 0; i < attrTargets.length; i++) {
      if (!shouldSkipElement(attrTargets[i])) translateAttrs(attrTargets[i]);
    }
  }

  function translateTree(root) {
    root = root || document.body;
    applying = true;
    detachObserver();
    try { walk(root); } finally {
      attachObserver();
      applying = false;
    }
  }

  function syncControls() {
    var selects = document.querySelectorAll("[data-i18n-switch]");
    for (var i = 0; i < selects.length; i++) {
      if (selects[i].value !== lang) selects[i].value = lang;
    }
  }

  function applyDocumentDirection() {
    var html = document.documentElement;
    html.setAttribute("lang", lang);
    html.setAttribute("dir", RTL[lang] ? "rtl" : "ltr");
  }

  function setLanguage(code, opts) {
    opts = opts || {};
    code = isSupported(code) ? code : "en";
    var changed = code !== lang;
    lang = code;
    applyDocumentDirection();
    if (opts.persistLocal !== false) {
      try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) {}
    }
    translateTree(document.body);
    syncControls();
    if (changed || opts.force) {
      for (var i = 0; i < changeHandlers.length; i++) {
        try { changeHandlers[i](lang); } catch (e) {}
      }
    }
    return lang;
  }

  function onChange(cb) { if (typeof cb === "function") changeHandlers.push(cb); }
  function getLanguage() { return lang; }
  function storedLanguage() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  function scheduleTranslate(nodes) {
    if (lang === "en") return;
    for (var i = 0; i < nodes.length; i++) {
      // queue: translate on next frame to batch bursts of DOM writes.
    }
    if (rafPending) return;
    rafPending = true;
    (window.requestAnimationFrame || window.setTimeout)(function () {
      rafPending = false;
      translateTree(document.body);
    }, 16);
  }

  function detachObserver() { if (observer) observer.disconnect(); }
  function attachObserver() {
    if (!observer || !document.body) return;
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  function startObserver() {
    if (!window.MutationObserver || !document.body) return;
    observer = new MutationObserver(function (mutations) {
      if (applying || lang === "en") return;
      scheduleTranslate(mutations);
    });
    attachObserver();
  }

  function init(opts) {
    opts = opts || {};
    var initial = storedLanguage();
    if (!isSupported(initial)) initial = isSupported(opts.fallback) ? opts.fallback : "en";
    // Apply immediately (no local persist on cold load when value came from default).
    setLanguage(initial, { persistLocal: storedLanguage() != null, force: true });
    startObserver();
    return lang;
  }

  window.I18N = {
    init: init,
    setLanguage: setLanguage,
    translateTree: translateTree,
    t: t,
    onChange: onChange,
    getLanguage: getLanguage,
    storedLanguage: storedLanguage,
    supported: SUPPORTED.slice(),
    dict: DICTS
  };

  // Apply direction/lang as early as possible to reduce flash before init().
  (function earlyApply() {
    var stored = storedLanguage();
    if (isSupported(stored)) {
      lang = stored;
      applyDocumentDirection();
    }
  })();
})();
