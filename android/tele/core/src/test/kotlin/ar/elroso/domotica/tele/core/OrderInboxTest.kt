package ar.elroso.domotica.tele.core

import org.junit.Assert.assertEquals
import org.junit.Test

class OrderInboxTest {

    @Test
    fun anOrderIsHandedOnlyOnce() {
        val inbox = OrderInbox()

        assertEquals(listOf(Order(1, OrderKind.STOP)), inbox.sort(listOf(Order(1, OrderKind.STOP))).fresh)
        assertEquals(emptyList<Order>(), inbox.sort(listOf(Order(1, OrderKind.STOP))).fresh)
    }

    @Test
    fun freshOrdersComeBySeq() {
        val inbox = OrderInbox()

        val fresh = inbox.sort(listOf(Order(3, OrderKind.STOP), Order(2, OrderKind.SHOW, "u"), Order(3, OrderKind.STOP))).fresh

        assertEquals(listOf(2L, 3L), fresh.map { it.seq })
    }

    @Test
    fun anOrderThatArrivesAgainIsRepeated() {
        val inbox = OrderInbox()
        inbox.sort(listOf(Order(1, OrderKind.STOP)))

        val sorted = inbox.sort(listOf(Order(2, OrderKind.STOP), Order(1, OrderKind.STOP), Order(2, OrderKind.STOP)))

        assertEquals(listOf(Order(2, OrderKind.STOP)), sorted.fresh)
        assertEquals(listOf(Order(1, OrderKind.STOP)), sorted.repeated)
    }

    @Test
    fun remembersOnlyTheLastSeqs() {
        val inbox = OrderInbox(keep = 2)
        inbox.sort(listOf(Order(1, OrderKind.STOP), Order(2, OrderKind.STOP), Order(3, OrderKind.STOP)))

        assertEquals(listOf(1L), inbox.sort(listOf(Order(1, OrderKind.STOP), Order(3, OrderKind.STOP))).fresh.map { it.seq })
    }
}
