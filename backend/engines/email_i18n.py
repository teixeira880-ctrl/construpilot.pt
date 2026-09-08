"""Traductions des emails transactionnels ConstruPilot (7 langues).

Emails couverts : réinitialisation de mot de passe, code 2FA, relances de
factures impayées (J+7 / J+15). Fallback FR si une clé/langue est absente.
"""

SUPPORTED = ["fr", "en", "es", "pt", "it", "de", "ar"]

EMAILS: dict[str, dict[str, str]] = {
    "fr": {
        "reset.subject_has": "Réinitialisation de votre mot de passe ConstruPilot",
        "reset.subject_set": "Définissez votre mot de passe ConstruPilot",
        "reset.greeting": "Bonjour {name},",
        "reset.intro_has": "Vous avez demandé la réinitialisation de votre mot de passe ConstruPilot.",
        "reset.intro_set": "Vous pouvez définir un mot de passe pour votre compte ConstruPilot (vous pourrez ainsi vous connecter par email en plus de Google).",
        "reset.cta_has": "Choisir un nouveau mot de passe",
        "reset.cta_set": "Définir mon mot de passe",
        "reset.note": "Ce lien est valable 1 heure et ne peut être utilisé qu'une fois. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.",
        "twofa.subject": "{code} — votre code de connexion ConstruPilot",
        "twofa.greeting": "Bonjour {name},",
        "twofa.line": "Votre code de connexion ConstruPilot :",
        "twofa.note": "Valable 10 minutes. Si vous n'êtes pas à l'origine de cette connexion, changez votre mot de passe immédiatement.",
        "invrem.subject": "Rappel — facture {number} en attente de règlement",
        "invrem.title": "Facture {number} en attente",
        "invrem.greeting": "Bonjour {name},",
        "invrem.body1": "Sauf erreur de notre part, la facture {number}, d'un montant restant dû de {amount}, n'a pas encore été réglée.",
        "invrem.body2": "Vous en trouverez une copie en pièce jointe. Merci de procéder au règlement dès que possible.",
    },
    "en": {
        "reset.subject_has": "Reset your ConstruPilot password",
        "reset.subject_set": "Set your ConstruPilot password",
        "reset.greeting": "Hello {name},",
        "reset.intro_has": "You requested to reset your ConstruPilot password.",
        "reset.intro_set": "You can set a password for your ConstruPilot account (so you can sign in with email as well as Google).",
        "reset.cta_has": "Choose a new password",
        "reset.cta_set": "Set my password",
        "reset.note": "This link is valid for 1 hour and can only be used once. If you didn't request this, please ignore this email.",
        "twofa.subject": "{code} — your ConstruPilot sign-in code",
        "twofa.greeting": "Hello {name},",
        "twofa.line": "Your ConstruPilot sign-in code:",
        "twofa.note": "Valid for 10 minutes. If you didn't try to sign in, change your password immediately.",
        "invrem.subject": "Reminder — invoice {number} awaiting payment",
        "invrem.title": "Invoice {number} outstanding",
        "invrem.greeting": "Hello {name},",
        "invrem.body1": "Unless we're mistaken, invoice {number}, with an outstanding balance of {amount}, has not yet been paid.",
        "invrem.body2": "A copy is attached. Please proceed with payment as soon as possible.",
    },
    "es": {
        "reset.subject_has": "Restablece tu contraseña de ConstruPilot",
        "reset.subject_set": "Define tu contraseña de ConstruPilot",
        "reset.greeting": "Hola {name}:",
        "reset.intro_has": "Has solicitado restablecer tu contraseña de ConstruPilot.",
        "reset.intro_set": "Puedes definir una contraseña para tu cuenta de ConstruPilot (así podrás iniciar sesión por email además de con Google).",
        "reset.cta_has": "Elegir una nueva contraseña",
        "reset.cta_set": "Definir mi contraseña",
        "reset.note": "Este enlace es válido durante 1 hora y solo puede usarse una vez. Si no has hecho esta solicitud, ignora este correo.",
        "twofa.subject": "{code} — tu código de acceso a ConstruPilot",
        "twofa.greeting": "Hola {name}:",
        "twofa.line": "Tu código de acceso a ConstruPilot:",
        "twofa.note": "Válido 10 minutos. Si no has intentado iniciar sesión, cambia tu contraseña de inmediato.",
        "invrem.subject": "Recordatorio — factura {number} pendiente de pago",
        "invrem.title": "Factura {number} pendiente",
        "invrem.greeting": "Hola {name}:",
        "invrem.body1": "Salvo error por nuestra parte, la factura {number}, con un importe pendiente de {amount}, aún no ha sido abonada.",
        "invrem.body2": "Adjuntamos una copia. Le rogamos que efectúe el pago lo antes posible.",
    },
    "pt": {
        "reset.subject_has": "Redefina a sua palavra-passe ConstruPilot",
        "reset.subject_set": "Defina a sua palavra-passe ConstruPilot",
        "reset.greeting": "Olá {name},",
        "reset.intro_has": "Solicitou a redefinição da sua palavra-passe ConstruPilot.",
        "reset.intro_set": "Pode definir uma palavra-passe para a sua conta ConstruPilot (assim poderá iniciar sessão por email além do Google).",
        "reset.cta_has": "Escolher uma nova palavra-passe",
        "reset.cta_set": "Definir a minha palavra-passe",
        "reset.note": "Este link é válido durante 1 hora e só pode ser usado uma vez. Se não fez este pedido, ignore este email.",
        "twofa.subject": "{code} — o seu código de acesso ConstruPilot",
        "twofa.greeting": "Olá {name},",
        "twofa.line": "O seu código de acesso ConstruPilot:",
        "twofa.note": "Válido por 10 minutos. Se não tentou iniciar sessão, altere já a sua palavra-passe.",
        "invrem.subject": "Lembrete — fatura {number} a aguardar pagamento",
        "invrem.title": "Fatura {number} em dívida",
        "invrem.greeting": "Olá {name},",
        "invrem.body1": "Salvo erro da nossa parte, a fatura {number}, com um montante em dívida de {amount}, ainda não foi paga.",
        "invrem.body2": "Segue uma cópia em anexo. Agradecemos que proceda ao pagamento o mais breve possível.",
    },
    "it": {
        "reset.subject_has": "Reimposta la tua password ConstruPilot",
        "reset.subject_set": "Imposta la tua password ConstruPilot",
        "reset.greeting": "Ciao {name},",
        "reset.intro_has": "Hai richiesto la reimpostazione della tua password ConstruPilot.",
        "reset.intro_set": "Puoi impostare una password per il tuo account ConstruPilot (così potrai accedere via email oltre che con Google).",
        "reset.cta_has": "Scegli una nuova password",
        "reset.cta_set": "Imposta la mia password",
        "reset.note": "Questo link è valido per 1 ora e può essere usato una sola volta. Se non hai fatto questa richiesta, ignora questa email.",
        "twofa.subject": "{code} — il tuo codice di accesso ConstruPilot",
        "twofa.greeting": "Ciao {name},",
        "twofa.line": "Il tuo codice di accesso ConstruPilot:",
        "twofa.note": "Valido 10 minuti. Se non hai tentato l'accesso, cambia subito la tua password.",
        "invrem.subject": "Promemoria — fattura {number} in attesa di pagamento",
        "invrem.title": "Fattura {number} da saldare",
        "invrem.greeting": "Ciao {name},",
        "invrem.body1": "Salvo errori da parte nostra, la fattura {number}, con un importo residuo di {amount}, non è ancora stata saldata.",
        "invrem.body2": "Trovi una copia in allegato. Ti preghiamo di procedere al pagamento al più presto.",
    },
    "de": {
        "reset.subject_has": "Setzen Sie Ihr ConstruPilot-Passwort zurück",
        "reset.subject_set": "Legen Sie Ihr ConstruPilot-Passwort fest",
        "reset.greeting": "Hallo {name},",
        "reset.intro_has": "Sie haben das Zurücksetzen Ihres ConstruPilot-Passworts angefordert.",
        "reset.intro_set": "Sie können ein Passwort für Ihr ConstruPilot-Konto festlegen (so können Sie sich neben Google auch per E-Mail anmelden).",
        "reset.cta_has": "Neues Passwort wählen",
        "reset.cta_set": "Mein Passwort festlegen",
        "reset.note": "Dieser Link ist 1 Stunde gültig und kann nur einmal verwendet werden. Falls Sie dies nicht angefordert haben, ignorieren Sie diese E-Mail.",
        "twofa.subject": "{code} — Ihr ConstruPilot-Anmeldecode",
        "twofa.greeting": "Hallo {name},",
        "twofa.line": "Ihr ConstruPilot-Anmeldecode:",
        "twofa.note": "10 Minuten gültig. Falls Sie sich nicht anmelden wollten, ändern Sie sofort Ihr Passwort.",
        "invrem.subject": "Erinnerung — Rechnung {number} noch offen",
        "invrem.title": "Rechnung {number} offen",
        "invrem.greeting": "Hallo {name},",
        "invrem.body1": "Sofern kein Irrtum vorliegt, wurde die Rechnung {number} mit einem offenen Betrag von {amount} noch nicht beglichen.",
        "invrem.body2": "Eine Kopie finden Sie im Anhang. Bitte begleichen Sie den Betrag schnellstmöglich.",
    },
    "ar": {
        "reset.subject_has": "إعادة تعيين كلمة مرور ConstruPilot",
        "reset.subject_set": "تعيين كلمة مرور ConstruPilot",
        "reset.greeting": "مرحبًا {name}،",
        "reset.intro_has": "لقد طلبت إعادة تعيين كلمة مرور ConstruPilot الخاصة بك.",
        "reset.intro_set": "يمكنك تعيين كلمة مرور لحسابك في ConstruPilot (لتتمكن من تسجيل الدخول بالبريد الإلكتروني إضافةً إلى Google).",
        "reset.cta_has": "اختيار كلمة مرور جديدة",
        "reset.cta_set": "تعيين كلمة المرور",
        "reset.note": "هذا الرابط صالح لمدة ساعة واحدة ولا يمكن استخدامه إلا مرة واحدة. إذا لم تطلب ذلك، فتجاهل هذه الرسالة.",
        "twofa.subject": "{code} — رمز تسجيل الدخول إلى ConstruPilot",
        "twofa.greeting": "مرحبًا {name}،",
        "twofa.line": "رمز تسجيل الدخول إلى ConstruPilot:",
        "twofa.note": "صالح لمدة 10 دقائق. إذا لم تحاول تسجيل الدخول، فغيّر كلمة المرور فورًا.",
        "invrem.subject": "تذكير — الفاتورة {number} في انتظار السداد",
        "invrem.title": "الفاتورة {number} غير مسددة",
        "invrem.greeting": "مرحبًا {name}،",
        "invrem.body1": "ما لم يكن هناك خطأ من جانبنا، فإن الفاتورة {number} بمبلغ متبقٍ قدره {amount} لم تُسدَّد بعد.",
        "invrem.body2": "تجدون نسخة مرفقة. يُرجى السداد في أقرب وقت ممكن.",
    },
}


def norm_lang(lang: str | None) -> str:
    lang = (lang or "pt").lower()[:2]
    return lang if lang in SUPPORTED else "pt"


def T(lang: str | None, key: str, **kw) -> str:
    """Traduz uma chave de email na língua indicada; fallback PT (padrão do produto) e depois a própria chave."""
    lg = norm_lang(lang)
    template = (EMAILS.get(lg, {}).get(key)
                or EMAILS["pt"].get(key)
                or EMAILS["fr"].get(key, key))
    try:
        return template.format(**kw) if kw else template
    except Exception:
        return template
