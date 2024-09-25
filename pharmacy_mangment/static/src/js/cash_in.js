odoo.define('pharmacy_mangment.CashIn', function(require) {
    'use strict';

    const PosComponent = require('point_of_sale.PosComponent');
    const ProductScreen = require('point_of_sale.ProductScreen');
    const { useListener } = require("@web/core/utils/hooks");
    const Registries = require('point_of_sale.Registries');

    class CashIn extends PosComponent {
        setup() {
            super.setup();
            useListener('click', this.onClick);
        }
        async onClick() {
            try {
                const result = await this.rpc({
                    model: 'pos.session',
                    method: 'print_cash_transaction_in',
                    args: [[this.env.pos.pos_session.id]],
                });

                if (result && result.url) {
                    window.open(result.url, '_blank');
                } else {
                    console.error("Failed to get the PDF URL.");
                }
            } catch (error) {
                console.error("Error printing cash transaction in", error);
            }
        }
    }
    CashIn.template = 'CashIn';

    ProductScreen.addControlButton({
        component: CashIn,
        condition: function() {
            return true;
        },
    });

    Registries.Component.add(CashIn);

    return CashIn;
});

