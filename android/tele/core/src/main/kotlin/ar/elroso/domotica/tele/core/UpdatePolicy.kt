package ar.elroso.domotica.tele.core

/** La última versión ofrecida para instalar y cuándo. */
data class Offer(val versionCode: Int, val at: Long)

/** Guarda y devuelve la última oferta hecha y la última versión rechazada. */
interface OfferLog {
    fun last(): Offer?

    fun save(offer: Offer)

    /** El `versionCode` que falló al instalarse de forma definitiva, o null. */
    fun rejected(): Int?

    fun reject(versionCode: Int)
}

/** La última oferta y el último rechazo en memoria. */
class MemoryOfferLog : OfferLog {
    @Volatile
    private var offer: Offer? = null

    @Volatile
    private var rejected: Int? = null

    override fun last(): Offer? = offer

    override fun save(offer: Offer) {
        this.offer = offer
    }

    override fun rejected(): Int? = rejected

    override fun reject(versionCode: Int) {
        rejected = versionCode
    }
}

/** Qué hacer con una versión publicada. */
enum class UpdateDecision {
    OFFER,
    CURRENT,
    REJECTED,
    RECENT,
    ALARM,
    PLAYING,
    ASLEEP,
    NOT_ALLOWED,
}

/** Decide si se ofrece instalar una versión publicada sobre la propia (`own`). */
class UpdatePolicy(
    private val own: Int,
    private val offers: OfferLog = MemoryOfferLog(),
    private val now: () -> Long = System::currentTimeMillis,
    private val retryMs: Long = RETRY_MS,
) {
    companion object {
        /** Cuánto se espera para volver a ofrecer la misma versión. */
        const val RETRY_MS = 6 * 3_600_000L
    }

    fun decide(release: Release, alarm: Long?, playing: Boolean, awake: Boolean, allowed: Boolean): UpdateDecision = when {
        release.versionCode <= own -> UpdateDecision.CURRENT
        release.versionCode == offers.rejected() -> UpdateDecision.REJECTED
        recent(release) -> UpdateDecision.RECENT
        alarm != null -> UpdateDecision.ALARM
        playing -> UpdateDecision.PLAYING
        !awake -> UpdateDecision.ASLEEP
        !allowed -> UpdateDecision.NOT_ALLOWED
        else -> UpdateDecision.OFFER
    }

    /** Anota que esa versión se acaba de ofrecer. */
    fun offered(release: Release) {
        offers.save(Offer(release.versionCode, now()))
    }

    /** Anota que esa versión falló al instalarse de forma definitiva: no se vuelve a ofrecer. */
    fun rejected(versionCode: Int) {
        offers.reject(versionCode)
    }

    private fun recent(release: Release): Boolean {
        val last = offers.last()?.takeIf { it.versionCode == release.versionCode } ?: return false
        return now() - last.at in 0 until retryMs
    }
}
