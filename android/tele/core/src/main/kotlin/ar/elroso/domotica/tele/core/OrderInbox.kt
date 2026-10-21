package ar.elroso.domotica.tele.core

/** Recuerda los últimos `seq` procesados y separa las órdenes nuevas de las repetidas. */
class OrderInbox(private val keep: Int = 64) {
    private val seen = LinkedHashSet<Long>()

    /** Las órdenes de un `poll`: las nuevas por procesar y las ya procesadas que el CT repite. */
    data class Sorted(val fresh: List<Order>, val repeated: List<Order>)

    /** Separa las órdenes, por `seq`, y anota las nuevas como procesadas. */
    fun sort(orders: List<Order>): Sorted {
        val unique = orders.distinctBy { it.seq }.sortedBy { it.seq }
        val (repeated, fresh) = unique.partition { it.seq in seen }
        fresh.forEach { seen += it.seq }
        while (seen.size > keep) seen.remove(seen.first())
        return Sorted(fresh, repeated)
    }
}
