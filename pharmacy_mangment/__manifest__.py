{
    'name':'Pharmacy Management',
    'depends': ['base', 'product','stock','mail','purchase','point_of_sale', 'web'],
    'category':'Inventory',
    'summary':'POS cash in & cash out - Purchase Order Approval',
    'data':[
        'security/ir.model.access.csv',
        'security/purchase_group.xml',
        'views/pharmacist_shape_views.xml',
        'views/effective_material_views.xml',
        'views/product_view.xml',
        'wizard/reason_wizerd_reject.xml',
        'views/menu.xml',
        'views/quotation_reject.xml',
        'views/purchase_approvel_inherit.xml',
        'views/setting_view.xml',
            ]  ,

        'assets': {
        'point_of_sale.assets': [
             
            'pharmacy_mangment/static/src/xml/cash_buttons.xml',  
            'pharmacy_mangment/static/src/js/cash_in.js',  
            'pharmacy_mangment/static/src/js/cash_out.js',  
             'pharmacy_mangment/static/src/js/pos_buttons.js',  
            'pharmacy_mangment/static/src/xml/pos_template.xml', 

        ],
      
        
    },
      'author':'Petra Software',
    'company': 'Petra Software',
    'maintainer': 'Petra Software',
    'website':'www.t-petra.com',
     'license': 'LGPL-3',
     'price':100,
    'currency':'USD'   

}

