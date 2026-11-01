"""Genera el dataset SINTÉTICO de motivos de contacto de NexaBank (empresa ficticia).

La Fase I definió que el asistente "genera automáticamente un resumen y clasificación
del motivo de contacto para el CRM", pero no entregó un corpus de texto. Este script
construye uno de forma reproducible (semilla fija) a partir de frases núcleo escritas
a mano por intención.

Para evitar fuga de información (data leakage), la partición train/test se hace por
FRASE NÚCLEO: las frases usadas en test nunca aparecen en entrenamiento, solo comparten
saludos/cierres genéricos. Así la métrica de test mide generalización a redacciones nuevas.

Uso:
    python training/generate_dataset.py
Salida:
    data/intents_train.csv, data/intents_test.csv
"""

from __future__ import annotations

import csv
import random
import unicodedata
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TRAIN_PER_CLASS = 120
TEST_PER_CLASS = 30
TEST_CORES_PER_CLASS = 4

MONTOS = ["350", "1,200", "2,499.90", "5,000", "899", "15,000", "12,750", "640"]
COMERCIOS = ["una tienda en línea", "Amazon", "una gasolinera", "Netflix", "un restaurante", "Mercado Libre", "un supermercado", "Uber"]
FECHAS = ["ayer", "el lunes", "el 3 de octubre", "la semana pasada", "hoy en la mañana", "el día 15"]

OPENERS = ["", "Hola,", "Buenas tardes,", "Buen día,", "Oiga,", "Disculpe,", "Hola buenas noches,", "Qué tal,", "Señorita,", "Joven,"]
CLOSERS = ["", "por favor", "¿me pueden ayudar?", "gracias", "es urgente", "¿qué hago?", "necesito ayuda", "¿cómo le hago?", "quedo atento", "¿me apoya?"]

CORES: dict[str, list[str]] = {
    "consulta_saldo": [
        "quiero saber cuánto dinero tengo en mi cuenta",
        "me puede decir mi saldo disponible",
        "necesito revisar los movimientos de mi tarjeta de débito",
        "cuánto tengo en mi cuenta de nómina",
        "quiero consultar los últimos movimientos de {fecha}",
        "necesito mi estado de cuenta del mes pasado",
        "no me llega el estado de cuenta a mi correo",
        "me pueden mandar una constancia de saldo",
        "ocupo saber si ya me depositaron la nómina",
        "quiero ver mi saldo pero no sé dónde se consulta",
        "necesito estados de cuenta de hace dos años",
        "cuánto dinero me queda después de {fecha}",
    ],
    "aclaracion_cargo": [
        "me aparece un cargo de {monto} pesos que yo no hice",
        "no reconozco un cobro de {comercio} por {monto}",
        "me cobraron dos veces la misma compra en {comercio}",
        "hay un cargo en mi tarjeta que no reconozco de {fecha}",
        "quiero levantar una aclaración por un cobro indebido",
        "me cobraron una comisión que no me corresponde",
        "pagué en {comercio} y me descontaron el doble",
        "me hicieron un cargo de {monto} y nunca recibí el producto",
        "aparece una compra de {comercio} que no realicé",
        "me cobraron una anualidad que me dijeron que no tenía",
        "quiero que me devuelvan un cargo duplicado de {monto}",
        "no reconozco una domiciliación que me cobran cada mes",
    ],
    "bloqueo_tarjeta": [
        "me robaron la cartera con mi tarjeta",
        "perdí mi tarjeta de débito y quiero bloquearla",
        "se me extravió la tarjeta de crédito {fecha}",
        "necesito cancelar mi tarjeta porque me la robaron",
        "no encuentro mi tarjeta, quiero apagarla",
        "el cajero se quedó con mi tarjeta",
        "se me bloqueó la tarjeta por poner mal el NIP",
        "quiero reponer mi tarjeta porque se perdió",
        "me asaltaron y se llevaron mis tarjetas",
        "dejé mi tarjeta olvidada en {comercio} y no la encuentro",
        "quiero bloquear la tarjeta de inmediato, la extravié",
        "cómo desbloqueo mi tarjeta, ya no me deja pagar",
    ],
    "posible_fraude": [
        "me llamaron del banco pidiéndome el código que me llegó por mensaje",
        "me llegó un mensaje con un enlace para actualizar mis datos y lo abrí",
        "alguien hizo transferencias desde mi cuenta sin mi permiso",
        "creo que me clonaron la tarjeta",
        "me hablaron diciendo que eran de NexaBank y les di mi NIP",
        "recibí un correo raro que dice que mi cuenta será cancelada",
        "sacaron dinero de mi cuenta en un cajero que no conozco",
        "creo que alguien está usando mi identidad para pedir créditos",
        "me hackearon la app y movieron mi dinero",
        "una persona me pidió el token por teléfono y se lo di",
        "metí mis datos en una página que parecía del banco",
        "vaciaron mi cuenta con compras en el extranjero que yo no hice",
    ],
    "transferencias": [
        "hice una transferencia SPEI y no le ha llegado a la otra persona",
        "cómo hago una transferencia a otro banco",
        "transferí dinero a una cuenta equivocada",
        "quiero aumentar mi límite de transferencias diarias",
        "me dice que la CLABE es incorrecta al transferir",
        "envié {monto} pesos {fecha} y todavía no se refleja",
        "necesito la clave de rastreo de mi transferencia",
        "me equivoqué en un dígito de la cuenta al transferir",
        "no me deja enviar más de cincuenta mil pesos",
        "me iban a depositar por SPEI y no me ha llegado",
        "cómo doy de alta una cuenta para transferir",
        "quiero que me regresen una transferencia que mandé por error",
    ],
    "credito_prestamo": [
        "quiero solicitar un préstamo personal",
        "qué requisitos piden para un crédito",
        "me interesa un crédito hipotecario para comprar casa",
        "quiero liquidar mi préstamo antes de tiempo",
        "cuánto debo de mi crédito personal",
        "no puedo pagar mi préstamo este mes, qué opciones tengo",
        "me aparece una oferta de préstamo preaprobado en la app",
        "quiero hacer un pago adelantado a capital",
        "necesito la carta finiquito de mi crédito",
        "cuál es la tasa de interés de los préstamos",
        "quiero reestructurar mi deuda",
        "me pueden prestar {monto} pesos a plazos",
    ],
    "tarjeta_credito": [
        "cuál es la fecha de corte de mi tarjeta de crédito",
        "cuánto tengo que pagar para no generar intereses",
        "quiero que me aumenten la línea de crédito",
        "cuándo es mi fecha límite de pago",
        "si pago el mínimo me cobran intereses",
        "quiero pasar una compra a meses sin intereses",
        "cómo pago mi tarjeta de crédito desde la app",
        "hice el pago de mi tarjeta y no se ve reflejado",
        "quiero diferir una compra de {monto} a pagos fijos",
        "por qué me bajaron el límite de mi tarjeta",
        "cuánto debo en total de mi tarjeta de crédito",
        "no entiendo los intereses que me cobraron en el corte",
    ],
    "actualizacion_datos": [
        "quiero cambiar mi número de celular",
        "me cambié de domicilio y quiero actualizarlo",
        "necesito actualizar mi correo electrónico",
        "mi INE ya venció, cómo la actualizo",
        "quiero agregar un beneficiario a mi cuenta",
        "cambié de teléfono de casa y quiero registrarlo",
        "tengo mal escrito mi nombre en la cuenta",
        "quiero modificar a los beneficiarios de mi cuenta",
        "cómo cambio la dirección donde me llegan los estados de cuenta",
        "ya no uso ese correo, quiero poner otro",
        "me pidieron actualizar mis datos, qué documentos necesito",
        "quiero registrar mi nuevo comprobante de domicilio",
    ],
    "banca_digital": [
        "olvidé mi contraseña de la app",
        "no puedo entrar a la banca en línea",
        "me bloquearon el usuario por intentos fallidos",
        "cambié de celular y no sé cómo activar la app",
        "la aplicación se cierra cuando intento entrar",
        "no me llega el código SMS para activar la app",
        "cómo activo el NexaToken en mi nuevo teléfono",
        "me sale un error al iniciar sesión",
        "la app no me deja hacer nada, se queda cargando",
        "perdí mi celular y tenía la app instalada",
        "quiero registrarme en la banca en línea",
        "no reconoce mi huella para entrar a la app",
    ],
    "queja_servicio": [
        "quiero poner una queja por la mala atención en sucursal",
        "llevo una hora esperando y nadie me resuelve, es pésimo servicio",
        "quiero hablar con un supervisor, el ejecutivo fue grosero",
        "estoy muy molesto, ya es la quinta vez que llamo por lo mismo",
        "voy a ir a CONDUSEF si no me resuelven",
        "quiero levantar una queja formal",
        "me trataron muy mal en la sucursal {fecha}",
        "nunca me respondieron la queja que puse hace un mes",
        "el servicio de este banco es un desastre, quiero reportarlo",
        "me prometieron una respuesta y nadie me llamó",
        "quiero que quede registrado mi descontento",
        "exijo hablar con alguien que sí me resuelva",
    ],
}

# Ampliación v2: más variedad léxica (se agregan al conjunto de frases núcleo antes de la partición).
EXTRA_CORES: dict[str, list[str]] = {
    "consulta_saldo": [
        "ya me cayó el depósito o todavía no",
        "quiero checar mis movimientos de esta semana",
        "no sé cuánto me queda en la tarjeta de débito",
        "pásame el saldo de mi cuenta por favor",
        "quiero descargar mi estado de cuenta en pdf",
        "me pueden decir cuánto tengo disponible para retirar",
        "necesito una constancia de retenciones",
        "en la app no me aparecen mis movimientos recientes",
        "cuánto dinero hay en mi cuenta de ahorro",
        "quiero el historial de movimientos de los últimos tres meses"
    ],
    "aclaracion_cargo": [
        "me descontaron dinero por algo que nunca compré",
        "hay un pago que no autoricé en mi estado de cuenta",
        "el cajero no me dio el dinero pero sí me lo descontó",
        "me cobraron {monto} de más en {comercio}",
        "cancelé una suscripción y me la siguen cobrando",
        "no reconozco un retiro de {monto} pesos",
        "quiero disputar un cargo de {comercio}",
        "me aplicaron un cobro por {monto} que no es mío",
        "el comercio me hizo un reembolso y no lo veo",
        "quiero reclamar un cobro que no me corresponde"
    ],
    "bloqueo_tarjeta": [
        "se me cayó la tarjeta en la calle",
        "quiero reportar mi tarjeta como robada",
        "alguien se llevó mi bolso con la tarjeta adentro",
        "necesito una tarjeta nueva porque la perdí",
        "quiero apagar la tarjeta mientras la busco",
        "mi tarjeta se quedó atorada en el cajero",
        "me quitaron la tarjeta, bloquéenla por favor",
        "olvidé la tarjeta en un taxi",
        "quiero dar de baja la tarjeta extraviada",
        "cuánto tarda en llegar la reposición de mi tarjeta"
    ],
    "posible_fraude": [
        "me están marcando de un número que dice ser del banco y me piden datos",
        "me llegó un whatsapp pidiendo mi contraseña",
        "creo que fui víctima de un fraude",
        "hicieron compras con mi tarjeta y yo la tengo conmigo",
        "me robaron la identidad y abrieron una cuenta a mi nombre",
        "di mis datos en un enlace falso",
        "me engañaron por teléfono y transfirieron mi dinero",
        "alguien entró a mi banca en línea sin permiso",
        "me dijeron que mi cuenta estaba en riesgo y me pidieron el token",
        "me estafaron con un supuesto premio del banco"
    ],
    "transferencias": [
        "la transferencia aparece como enviada pero no llegó",
        "cuánto tarda una transferencia interbancaria",
        "quiero mandar dinero a otra cuenta",
        "no puedo registrar un nuevo beneficiario para transferir",
        "me rechazaron la transferencia y no sé por qué",
        "necesito el comprobante de la transferencia",
        "deposité a una CLABE equivocada",
        "me mandaron dinero de otro banco y no aparece",
        "quiero cambiar el límite para transferir",
        "cómo consulto el estado de un SPEI"
    ],
    "credito_prestamo": [
        "me pueden dar un préstamo",
        "cuánto me prestan si tengo nómina con ustedes",
        "quiero pagar por completo mi crédito",
        "necesito un crédito para mi negocio",
        "me atrasé en el pago de mi préstamo",
        "quiero saber el saldo para liquidar mi crédito",
        "me ofrecieron un crédito en la app, cómo lo acepto",
        "quiero un préstamo a 24 meses",
        "cómo hago para comprar una casa con crédito",
        "necesito un convenio de pago porque no me alcanza"
    ],
    "tarjeta_credito": [
        "cuándo tengo que pagar la tarjeta de crédito",
        "me cobraron intereses en mi tarjeta de crédito",
        "quiero subir el límite de mi tarjeta",
        "cómo pongo una compra a meses",
        "cuál es el pago mínimo de este mes",
        "ya pagué la tarjeta pero sigue apareciendo el adeudo",
        "qué día corta mi tarjeta",
        "quiero saber el saldo de mi tarjeta de crédito",
        "me rechazaron una compra por falta de línea de crédito",
        "cómo evito pagar intereses en la tarjeta"
    ],
    "actualizacion_datos": [
        "necesito cambiar mi correo registrado",
        "quiero poner mi nuevo número de teléfono",
        "me mudé, dónde actualizo mi dirección",
        "cómo agrego beneficiarios",
        "mi identificación está vencida",
        "quiero corregir mi fecha de nacimiento",
        "me casé y quiero cambiar mi apellido",
        "quiero cambiar el celular donde me llegan los avisos",
        "necesito actualizar mi expediente",
        "cuáles son los documentos para cambiar mi domicilio"
    ],
    "banca_digital": [
        "no me acuerdo de mi contraseña",
        "no puedo iniciar sesión en la app",
        "me salió que mi usuario está bloqueado",
        "compré otro celular y necesito pasar la app",
        "la app me marca error",
        "no recibo el mensaje con el código",
        "cómo descargo el token en mi celular",
        "la banca en línea no carga",
        "quiero cambiar mi contraseña de la app",
        "ya no tengo el teléfono donde estaba el token"
    ],
    "queja_servicio": [
        "quiero presentar una queja",
        "estoy harto de que no me resuelvan",
        "la atención fue pésima",
        "quiero reportar al ejecutivo que me atendió",
        "me colgaron la llamada y quiero quejarme",
        "me tienen dando vueltas y nadie resuelve",
        "quiero hablar con el gerente",
        "me siento muy mal atendido por el banco",
        "voy a presentar una reclamación en CONDUSEF",
        "no es posible que tarden tanto, quiero levantar un reporte"
    ]
}
for _label, _extra in EXTRA_CORES.items():
    CORES[_label] = CORES[_label] + _extra


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def render(core: str, rng: random.Random) -> str:
    text = core.format(monto=rng.choice(MONTOS), comercio=rng.choice(COMERCIOS), fecha=rng.choice(FECHAS))
    opener, closer = rng.choice(OPENERS), rng.choice(CLOSERS)
    parts = [p for p in (opener, text, closer) if p]
    sentence = " ".join(parts)
    # Ruido realista de chat: sin acentos, todo en minúsculas o sin mayúscula inicial.
    r = rng.random()
    if r < 0.25:
        sentence = strip_accents(sentence)
    elif r < 0.45:
        sentence = sentence.lower()
    return sentence[0].upper() + sentence[1:] if rng.random() < 0.6 else sentence


def build(rng: random.Random) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    train, test = [], []
    for label, cores in CORES.items():
        cores = cores[:]
        rng.shuffle(cores)
        test_cores, train_cores = cores[:TEST_CORES_PER_CLASS], cores[TEST_CORES_PER_CLASS:]
        for _ in range(TRAIN_PER_CLASS):
            core = rng.choice(train_cores)
            train.append((render(core, rng), label, f"{label}:{CORES[label].index(core)}"))
        for _ in range(TEST_PER_CLASS):
            core = rng.choice(test_cores)
            test.append((render(core, rng), label, f"{label}:{CORES[label].index(core)}"))
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def write_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["text", "label", "core_id"])
        writer.writerows(rows)


def main() -> None:
    rng = random.Random(SEED)
    train, test = build(rng)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(DATA_DIR / "intents_train.csv", train)
    write_csv(DATA_DIR / "intents_test.csv", test)
    print(f"train={len(train)} test={len(test)} clases={len(CORES)}")


if __name__ == "__main__":
    main()
