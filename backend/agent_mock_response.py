from fastapi.responses import JSONResponse

def mock_response():
  data = {
    "plan": {
      "title": "Your Personalised Plan for Having a Baby",
      "summary": "As a single parent expecting a baby while self-employed and on Universal Credit in England, you'll need to register the birth, claim child-related benefits, and explore childcare support. Some key actions have strict deadlines.",
      "steps": [
        {
            "title": "Step 1: Get maternity support and health entitlements",
            "summary": "As a single parent who is self-employed and on Universal Credit, you have access to key benefits and support. This plan outlines the steps you should take before, during, and after your baby arrives — including maternity support, registration, childcare costs, and income support updates.",
            "status": "Not started",
            "tasks": [
                {
                    "title": "Check if you qualify for Maternity Allowance",
                    "summary": "As a self-employed person, you may be eligible for Maternity Allowance instead of Statutory Maternity Pay. This provides up to 39 weeks of payment from the DWP.",
                    "callout": "Apply as soon as you are 26 weeks pregnant. Do not wait — the earlier you apply, the sooner payments can start.",
                    "methods": [
                        "online",
                        "post",
                        "phone"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": "Apply from 26 weeks pregnant; payments typically start 11 weeks before your due date",
                    "grant": None,
                    "gov_service_name": "Maternity Allowance",
                    "gov_service_url": "https://www.gov.uk/maternity-allowance",
                    "cost": 0,
                    "service_form_url": "https://www.gov.uk/apply-maternity-allowance",
                    "service_form_label": "Apply for Maternity Allowance",
                    "what_to_expect": "Maternity Allowance is designed for self-employed and recently employed workers who don't qualify for Statutory Maternity Pay. You typically need to have worked as self-employed for at least 2 of the last 3 years. You can apply from 26 weeks of pregnancy. The payment is usually paid weekly into your bank account. This is crucial for your income during maternity leave, so apply early.\n\nYou do not need to choose between Maternity Allowance and Universal Credit — you can claim both. However, your Maternity Allowance will be counted as income on your UC claim, which may reduce your UC payment.",
                    "requirements": [
                        "Your National Insurance number",
                        "Proof of self-employment (tax return or accounts)",
                        "Your bank details",
                        "Your baby's due date"
                    ]
                },
                {
                    "title": "Get a Maternity Exemption Certificate for free NHS prescriptions and dental",
                    "summary": "You are automatically entitled to free NHS prescriptions and dental treatment during pregnancy and for 12 months after your baby is born. Ask your midwife or GP for a Maternity Exemption Certificate (MatEx).",
                    "callout": "Request this as soon as you book in for antenatal care. Without it, you may have to pay for prescriptions and dental treatment.",
                    "methods": [
                        "in-person"
                    ],
                    "dept": "NHS",
                    "completed": False,
                    "location": "GP surgery or midwifery clinic",
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Maternity Exemption Certificate",
                    "gov_service_url": "https://www.nhs.uk/pregnancy/finding-out/free-nhs-prescriptions-and-dental-care/",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "The Maternity Exemption Certificate entitles you to free NHS prescriptions and dental treatment from the date you receive your positive pregnancy test through to 12 months after your baby is born. This is a valuable entitlement — it will save you on prescription charges and dental costs. You need to apply for the certificate, usually through your midwife when you book in for antenatal care, or through your GP. It's normally issued as a certificate card that you present to pharmacists and dentists.\n\nThis is universal — you don't need to meet any income tests or eligibility criteria. It's simply part of NHS maternity care.",
                    "requirements": [
                        "Your NHS number",
                        "Proof of pregnancy (booking appointment letter or positive pregnancy test)"
                    ]
                },
                {
                    "title": "Apply for Healthy Start vouchers",
                    "summary": "You can get prepaid cards worth £8.50/week for healthy food and milk during pregnancy, and £4.25/week per child under 1 after your baby is born. You're eligible because you're on Universal Credit.",
                    "callout": "Apply from 10 weeks pregnant. Do not wait — there's no deadline, but you want the support as early as possible.",
                    "methods": [
                        "online"
                    ],
                    "dept": "NHS",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Healthy Start vouchers",
                    "gov_service_url": "https://www.healthystart.nhs.uk/",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Healthy Start vouchers are loaded onto a prepaid card that you can use to buy fruit, vegetables, milk, and infant formula. During pregnancy, you'll get £8.50 per week. After your baby is born, you'll get £4.25 per week for each child under age 1 (increasing to £4.25 for children aged 1–3). You must be receiving a qualifying benefit (which you are, via Universal Credit) and be at least 10 weeks pregnant. The vouchers are a straightforward way to access healthy food and support your family's nutrition.\n\nYou can apply from 10 weeks of pregnancy. The process is quick and online. Cards typically arrive within 5–10 working days.",
                    "requirements": [
                        "Your National Insurance number",
                        "Proof of pregnancy or child's date of birth",
                        "Your bank details (for initial setup)"
                    ]
                }
            ]
        },
        {
            "title": "Step 2: Register the birth and apply for key baby benefits",
            "summary": "Within 42 days of birth, you must register your baby. At the same time, apply for Sure Start Grant (if first child), Child Benefit, and notify DWP about the new child for your Universal Credit.",
            "status": "Not started",
            "tasks": [
                {
                    "title": "Register your baby's birth",
                    "summary": "You have 42 days from birth to register your baby at your local register office. This is a legal requirement and unlocks access to benefits, free childcare, and other support.",
                    "callout": "Register within 42 days of birth. After this deadline, you may face penalties and the process becomes more complicated. Do not delay.",
                    "methods": [
                        "in-person",
                        "post"
                    ],
                    "dept": "GRO",
                    "completed": False,
                    "location": "Local register office (find yours via www.gov.uk/register-birth)",
                    "deadline": "Within 42 days of birth",
                    "grant": None,
                    "gov_service_name": "Register the birth",
                    "gov_service_url": "https://www.gov.uk/register-birth",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Birth registration is a straightforward legal process. You need to contact your local register office and book an appointment — most can be done within a few days. You'll need to provide details about the baby, yourself, and the other parent (if applicable). The registration is free. You'll receive a short birth certificate immediately, and you can order certified copies for a small fee if needed for school, passport applications, or benefits claims.\n\nRegistering the birth is crucial because it's required before you can claim Child Benefit, access free childcare entitlements, and claim Sure Start Grant. This is your top priority after the baby arrives.",
                    "requirements": [
                        "Baby's full name (if you've decided)",
                        "Your full name and address",
                        "Your partner's full name and address (if applicable)",
                        "Your National Insurance numbers",
                        "Medical card or hospital discharge papers with baby's details"
                    ]
                },
                {
                    "title": "Apply for Sure Start Maternity Grant",
                    "summary": "You can get a one-off payment of £500 to help with costs of a new baby. You're eligible because you're on Universal Credit. Usually available for the first child only.",
                    "callout": "Apply within 3 months of birth — if you miss this deadline, you cannot claim it. Do not delay after the baby arrives.",
                    "methods": [
                        "online",
                        "post"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": "Apply within 3 months of birth",
                    "grant": None,
                    "gov_service_name": "Sure Start Maternity Grant",
                    "gov_service_url": "https://www.gov.uk/sure-start-maternity-grant",
                    "cost": 0,
                    "service_form_url": "https://www.gov.uk/apply-sure-start-maternity-grant",
                    "service_form_label": "Apply for Sure Start Maternity Grant",
                    "what_to_expect": "Sure Start Maternity Grant is a one-off payment of £500. You must apply within 3 months of your baby's birth, and you should be on a qualifying benefit at the time of birth (which you are). For most families, this is only available for the first child, though there are some exceptions if you qualify as a lone parent or if your circumstances have changed significantly since the first child.\n\nYou can apply from 11 weeks before your due date right through to 3 months after birth. This gives you flexibility. The payment will be made into your bank account once approved.",
                    "requirements": [
                        "Your National Insurance number",
                        "Baby's birth certificate or confirmation of birth",
                        "Proof you're receiving a qualifying benefit (your UC award letter)",
                        "Your bank details"
                    ]
                },
                {
                    "title": "Apply for Child Benefit",
                    "summary": "You should claim Child Benefit for your baby. It's typically £25.60/week for the first child (higher for subsequent children). Payments are backdatable 3 months, so apply early.",
                    "callout": "Apply as soon as possible after birth. You can backdate your claim by up to 3 months, so don't delay — you could lose money.",
                    "methods": [
                        "online"
                    ],
                    "dept": "HMRC",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Child Benefit",
                    "gov_service_url": "https://www.gov.uk/child-benefit",
                    "cost": 0,
                    "service_form_url": "https://www.tax.service.gov.uk/child-benefit/view",
                    "service_form_label": "Apply for Child Benefit",
                    "what_to_expect": "Child Benefit is a payment for each child under 16 (or under 20 in approved education). You're entitled to it regardless of income or employment status — it's a universal benefit. For a first child, it's currently £25.60 per week. The payment is made every 4 weeks into your bank account. You can apply from the moment your baby is born (or even before if you're sure of your due date).\n\nChild Benefit does two important things: (1) it provides money for your child's care; and (2) it gives you and your child a link to the social security system, which protects your State Pension record. It's also a gate opener for other benefits like Tax-Free Childcare. If you or your partner earns over £60,000 per year, you may face a 'High Income Child Benefit Charge' — but on your current income, this won't apply.",
                    "requirements": [
                        "Your National Insurance number",
                        "Baby's date of birth and name",
                        "Your bank details",
                        "Details of any other children you're claiming for"
                    ]
                },
                {
                    "title": "Tell Universal Credit about your baby",
                    "summary": "Report your baby's birth to DWP within 1 month. Your UC will be recalculated to include the child element (currently £290/month for first child).",
                    "callout": "Report the birth within 1 month — if you miss the deadline, DWP may not backdate the payment. Do it immediately after registering the birth.",
                    "methods": [
                        "online",
                        "phone"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": "Report within 1 month of birth",
                    "grant": None,
                    "gov_service_name": "Universal Credit",
                    "gov_service_url": "https://www.gov.uk/universal-credit",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Once your baby is born, your Universal Credit entitlement will change. A new 'child element' (currently £290 per month for the first child, £205 for each subsequent child) will be added to your standard allowance. You must notify DWP of the birth within 1 month to avoid losing money.\n\nYou can report the birth online via your UC account, or by calling DWP. The payment will usually be increased from the first day of the month following the birth (so if your baby arrives on 15 March, the increase will typically start from 1 April). Your UC will also automatically factor in any Maternity Allowance you're receiving.",
                    "requirements": [
                        "Your National Insurance number",
                        "Baby's date of birth",
                        "Baby's name (optional for notification)"
                    ]
                }
            ]
        },
        {
            "title": "Step 3: Understand your free childcare options as your child grows",
            "summary": "As your child reaches 9 months to 4 years old, you'll become eligible for free childcare entitlements. The options depend on your child's age and your working hours.",
            "status": "Not started",
            "tasks": [
                {
                    "title": "Understand the universal 15 hours free childcare (9 months to 4 years)",
                    "summary": "From 9 months old, your baby will be eligible for 15 hours per week of free childcare. This is universal — everyone gets it. You set this up via your Childcare Choices account.",
                    "callout": "Set up your Childcare Choices account early (you can do it before your child turns 9 months). You must use the hours within the funding period or they are lost.",
                    "methods": [
                        "online"
                    ],
                    "dept": "HMRC",
                    "completed": False,
                    "location": None,
                    "deadline": "Sign up to Childcare Choices to enable the 15 hours from 9 months",
                    "grant": None,
                    "gov_service_name": "Free childcare — 15 hours",
                    "gov_service_url": "https://www.gov.uk/help-paying-childcare/free-childcare-and-education-for-2-to-4-year-olds",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "When your child turns 9 months old, you can access 15 hours per week of free childcare. This is a universal entitlement — there's no means test or eligibility criteria. You manage this through your Childcare Choices account, which is linked to your National Insurance number. You can use these hours with any Ofsted-registered childcare provider (nursery, childminder, preschool, etc.).\n\nTo use the hours, your chosen provider must be on the Ofsted Childcare Register or Early Years Register. You can check this online. The 15 hours can be used flexibly — you could do 5 hours on three days, or 3 hours across five days, depending on what works for your family. You can also combine the 15 hours with other childcare (paid for out of pocket, or via Tax-Free Childcare) to get more coverage if you're working.",
                    "requirements": [
                        "Your National Insurance number",
                        "Your child's date of birth",
                        "The Ofsted registration number of your chosen childcare provider"
                    ]
                },
                {
                    "title": "Check eligibility for free childcare for 2-year-olds (disadvantaged backgrounds)",
                    "summary": "If your 2-year-old is eligible, you may get 15 hours per week of free childcare from age 2 (not waiting until age 9 months). You're potentially eligible because you're on Universal Credit.",
                    "callout": "Apply to your local authority as soon as your child turns 2. Different councils have different application windows (some open at the start of term, others earlier). Do not assume your child is ineligible — on Universal Credit, you should qualify.",
                    "methods": [
                        "online",
                        "post",
                        "phone"
                    ],
                    "dept": "Local Authority",
                    "completed": False,
                    "location": None,
                    "deadline": "Apply when your child turns 2, before the start of the next funding term",
                    "grant": None,
                    "gov_service_name": "Free Childcare (disadvantaged 2-year-olds)",
                    "gov_service_url": "https://www.gov.uk/help-with-childcare-costs/free-childcare-2-year-olds",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "There is a separate programme for disadvantaged 2-year-olds offering 15 hours per week of free childcare. The criteria include: being on a qualifying benefit (you are), your child being in a looked-after situation, having an Education, Health and Care (EHC) plan, receiving Disability Living Allowance (DLA), or leaving care.\n\nBecause you're on Universal Credit, your child should be eligible from age 2. This is in addition to (not instead of) the universal 15 hours from age 9 months. So from age 2, you could potentially access 15 hours via this scheme, and then get a further 15 hours from age 9 months of age (making 30 hours total if you can work the hours).\n\nEligibility must be confirmed by your local authority. Contact your local council's Early Education and Childcare team to apply and check the exact criteria for your area (they vary slightly).",
                    "requirements": [
                        "Your National Insurance number",
                        "Proof of Universal Credit award (UC award letter)",
                        "Child's date of birth",
                        "Your child's postcode and local authority area"
                    ]
                },
                {
                    "title": "Consider Tax-Free Childcare if you're working enough hours",
                    "summary": "If you're self-employed and earning a reasonable income, Tax-Free Childcare could help with costs. The government tops up your savings by 25p for every £1 saved (max £500 per quarter per child).",
                    "callout": "You cannot use Tax-Free Childcare while claiming Universal Credit childcare costs element. If you're self-employed with very low income, UC childcare element may be better for you. Seek advice before switching.",
                    "methods": [
                        "online"
                    ],
                    "dept": "HMRC",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Tax-Free Childcare account",
                    "gov_service_url": "https://www.gov.uk/tax-free-childcare",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Tax-Free Childcare is a scheme where you open a special account and pay money in. For every £8 you pay in, the government adds £2 (a 25% top-up). The maximum top-up is £500 per quarter per child (or £1,000 if the child is disabled). You can then use the money to pay for registered childcare.\n\nEligibility requires: (1) you (and your partner, if applicable) are in work and earning at least the National Minimum Wage for 16 hours per week; (2) neither of you earns over £100,000 per year; and (3) neither of you is claiming the UC childcare element. Because you're self-employed on low income, you may not meet the working hours threshold. Tax-Free Childcare is also incompatible with Universal Credit's childcare element — if you're getting UC childcare support, you cannot use Tax-Free Childcare. Check your UC entitlement first.",
                    "requirements": [
                        "National Insurance number",
                        "Childcare provider's Ofsted registration number",
                        "Bank details to set up the account"
                    ]
                }
            ]
        },
        {
            "title": "Step 4: Update your Universal Credit as your situation changes",
            "summary": "As your baby grows and you return to work, you'll need to keep DWP updated about your earnings, childcare costs, and other changes.",
            "status": "Not started",
            "tasks": [
                {
                    "title": "Report any childcare costs to Universal Credit",
                    "summary": "If you're paying for childcare, you can claim back up to 85% of costs via your UC childcare element. Report these costs to DWP so you're reimbursed.",
                    "callout": "Keep all childcare invoices and receipts. DWP may ask you to prove you've paid for childcare. Without evidence, you won't get reimbursed.",
                    "methods": [
                        "online"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Universal Credit",
                    "gov_service_url": "https://www.gov.uk/universal-credit",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Universal Credit includes a 'childcare costs element' if you're in work and paying for childcare. You can claim back up to 85% of your eligible childcare costs, up to a maximum of £680 per month for one child (or £1,360 for two or more children). 'Eligible' childcare includes care from Ofsted-registered providers, childminders registered with a childcare agency, and some providers in Scotland and Wales.\n\nTo claim, you report your childcare costs to DWP when you notify them of your work earnings each month. You'll need receipts or invoices from your childcare provider showing you've paid for the care. The reimbursement happens automatically as part of your UC payment.",
                    "requirements": [
                        "Childcare provider's name and details",
                        "Monthly childcare costs and invoices",
                        "Proof that the provider is Ofsted-registered or approved"
                    ]
                },
                {
                    "title": "Report self-employment earnings monthly",
                    "summary": "As a self-employed UC claimant, you must report your trading income each month. DWP will apply the 'trading allowance' (currently £1,000/year) to reduce your assessable income.",
                    "callout": "Report honestly and on time each month. Failing to report can result in an overpayment, which you'll be asked to repay. It's important to get this right.",
                    "methods": [
                        "online"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Universal Credit",
                    "gov_service_url": "https://www.gov.uk/universal-credit",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Self-employed people on UC must report their profits each month. DWP will apply a 'trading allowance' — a set amount of income that's disregarded when calculating your UC. The allowance is £1,000 per year (or £83.33 per month if reported monthly). Any income above this is counted against your UC.\n\nFor example: if you earn £500 in a month, none of it counts (it's below the trading allowance). If you earn £1,500 in a month, £500 of it (£1,500 − £1,000 annual allowance) counts as income. The more you earn, the less UC you'll get, but you'll also be paying tax and National Insurance.\n\nYou report income via your UC journal each month. Keep good records of your earnings and business expenses — you may need them for tax and UC purposes.",
                    "requirements": [
                        "Monthly profit figures (income minus business expenses)",
                        "Records of invoices sent and payments received",
                        "Your business bank statements"
                    ]
                },
                {
                    "title": "Request a review of your UC if circumstances change",
                    "summary": "If your income drops significantly (e.g. because you've reduced your work for childcare), or if you have new costs or needs, request a UC recalculation. You're entitled to support if circumstances change.",
                    "callout": "Tell DWP about any change within 1 month. If you delay, you may miss out on extra money or face an overpayment. It's in your interest to report.",
                    "methods": [
                        "online",
                        "phone"
                    ],
                    "dept": "DWP",
                    "completed": False,
                    "location": None,
                    "deadline": None,
                    "grant": None,
                    "gov_service_name": "Universal Credit",
                    "gov_service_url": "https://www.gov.uk/universal-credit",
                    "cost": 0,
                    "service_form_url": None,
                    "service_form_label": None,
                    "what_to_expect": "Your UC is based on your circumstances at the time of assessment. If things change — for example, you earn less because you're looking after your new baby, or your childcare costs increase — you can ask DWP to recalculate your award. In many cases, this will increase your UC payment.\n\nCommon changes after having a baby include: lower earnings (especially if you reduce your working hours), childcare costs, and changes to your living situation. Always report these changes; it's your responsibility to keep DWP updated within 1 month of any change.",
                    "requirements": [
                        "Details of your changed circumstances",
                        "Evidence (payslips showing reduced income, childcare invoices, etc.)"
                    ]
                }
            ]
        }
    ],
      "reasoning": "You're in an excellent position because you're already claiming Universal Credit. Your self-employment means you won't get Statutory Maternity Pay, but you will likely qualify for Maternity Allowance instead. The most urgent actions are: (1) securing maternity support and registering the birth within 42 days; (2) applying for Sure Start Grant before the baby arrives; (3) registering your child for benefits like Child Benefit; and (4) understanding your childcare options as your child grows. Because you're on a low income, you'll also qualify for Healthy Start vouchers during pregnancy and while your child is young."
    },
    "agent_help": {
      "answer": "I can help you understand Tax-Free Childcare and guide you through the application process. Here's what I can do:\n\n**Full help:**\n- Explain how Tax-Free Childcare works (government adds £2 for every £8 you save)\n- Check your eligibility based on your work and income\n- Compare Tax-Free Childcare with Universal Credit childcare element to help you choose\n- Provide the direct link to apply\n\n**Partial help:**\n- Guide you to the online application (you'll need a Government Gateway account)\n- Help you understand the 15 hours and 30 hours free childcare entitlements\n- Explain how to check if your childcare provider is Ofsted-registered\n\n**Inform only:**\n- Child Benefit and birth registration (separate applications)\n\n**Important to know:**\n- You cannot use Tax-Free Childcare at the same time as the Universal Credit childcare element — you must choose one\n- Maximum government top-up is £500 per child per quarter (£2,000 per year, or £4,000 if your child is disabled)\n- You need to be in work earning at least National Minimum Wage for 16 hours per week\n- Neither parent can earn over £100,000 per year\n\nIf you have questions about your eligibility or need help comparing options, just ask."
    },
    "timestamp": "2026-07-17T16:24:58.948408+00:00",
    "status": "success"
  }

  return JSONResponse(data)
