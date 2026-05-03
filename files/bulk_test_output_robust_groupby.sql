-- Test #1 | aliasing=auto, jsonb=flat, field=direct, where=none, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items";

-- Test #2 | aliasing=auto, jsonb=flat, field=direct, where=none, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #3 | aliasing=auto, jsonb=flat, field=direct, where=none, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #4 | aliasing=auto, jsonb=flat, field=direct, where=simple, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #5 | aliasing=auto, jsonb=flat, field=direct, where=simple, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #6 | aliasing=auto, jsonb=flat, field=direct, where=simple, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #7 | aliasing=auto, jsonb=flat, field=direct, where=nested, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #8 | aliasing=auto, jsonb=flat, field=direct, where=nested, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #9 | aliasing=auto, jsonb=flat, field=direct, where=nested, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #10 | aliasing=auto, jsonb=flat, field=direct, where=in, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #11 | aliasing=auto, jsonb=flat, field=direct, where=in, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #12 | aliasing=auto, jsonb=flat, field=direct, where=in, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #13 | aliasing=auto, jsonb=flat, field=direct, where=between, order_by=none
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #14 | aliasing=auto, jsonb=flat, field=direct, where=between, order_by=single
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #15 | aliasing=auto, jsonb=flat, field=direct, where=between, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #16 | aliasing=auto, jsonb=flat, field=related, where=none, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id";

-- Test #17 | aliasing=auto, jsonb=flat, field=related, where=none, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #18 | aliasing=auto, jsonb=flat, field=related, where=none, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #19 | aliasing=auto, jsonb=flat, field=related, where=simple, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10;

-- Test #20 | aliasing=auto, jsonb=flat, field=related, where=simple, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #21 | aliasing=auto, jsonb=flat, field=related, where=simple, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #22 | aliasing=auto, jsonb=flat, field=related, where=nested, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100;

-- Test #23 | aliasing=auto, jsonb=flat, field=related, where=nested, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #24 | aliasing=auto, jsonb=flat, field=related, where=nested, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #25 | aliasing=auto, jsonb=flat, field=related, where=in, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3);

-- Test #26 | aliasing=auto, jsonb=flat, field=related, where=in, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #27 | aliasing=auto, jsonb=flat, field=related, where=in, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #28 | aliasing=auto, jsonb=flat, field=related, where=between, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #29 | aliasing=auto, jsonb=flat, field=related, where=between, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #30 | aliasing=auto, jsonb=flat, field=related, where=between, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #31 | aliasing=auto, jsonb=flat, field=aggregate, where=none, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #32 | aliasing=auto, jsonb=flat, field=aggregate, where=none, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #33 | aliasing=auto, jsonb=flat, field=aggregate, where=none, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #34 | aliasing=auto, jsonb=flat, field=aggregate, where=simple, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #35 | aliasing=auto, jsonb=flat, field=aggregate, where=simple, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #36 | aliasing=auto, jsonb=flat, field=aggregate, where=simple, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #37 | aliasing=auto, jsonb=flat, field=aggregate, where=nested, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #38 | aliasing=auto, jsonb=flat, field=aggregate, where=nested, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #39 | aliasing=auto, jsonb=flat, field=aggregate, where=nested, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #40 | aliasing=auto, jsonb=flat, field=aggregate, where=in, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #41 | aliasing=auto, jsonb=flat, field=aggregate, where=in, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #42 | aliasing=auto, jsonb=flat, field=aggregate, where=in, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #43 | aliasing=auto, jsonb=flat, field=aggregate, where=between, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #44 | aliasing=auto, jsonb=flat, field=aggregate, where=between, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #45 | aliasing=auto, jsonb=flat, field=aggregate, where=between, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #46 | aliasing=auto, jsonb=flat, field=expression, where=none, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items";

-- Test #47 | aliasing=auto, jsonb=flat, field=expression, where=none, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #48 | aliasing=auto, jsonb=flat, field=expression, where=none, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #49 | aliasing=auto, jsonb=flat, field=expression, where=simple, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #50 | aliasing=auto, jsonb=flat, field=expression, where=simple, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #51 | aliasing=auto, jsonb=flat, field=expression, where=simple, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #52 | aliasing=auto, jsonb=flat, field=expression, where=nested, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #53 | aliasing=auto, jsonb=flat, field=expression, where=nested, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #54 | aliasing=auto, jsonb=flat, field=expression, where=nested, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #55 | aliasing=auto, jsonb=flat, field=expression, where=in, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #56 | aliasing=auto, jsonb=flat, field=expression, where=in, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #57 | aliasing=auto, jsonb=flat, field=expression, where=in, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #58 | aliasing=auto, jsonb=flat, field=expression, where=between, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #59 | aliasing=auto, jsonb=flat, field=expression, where=between, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #60 | aliasing=auto, jsonb=flat, field=expression, where=between, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #61 | aliasing=auto, jsonb=json, field=direct, where=none, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items";

-- Test #62 | aliasing=auto, jsonb=json, field=direct, where=none, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #63 | aliasing=auto, jsonb=json, field=direct, where=none, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #64 | aliasing=auto, jsonb=json, field=direct, where=simple, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #65 | aliasing=auto, jsonb=json, field=direct, where=simple, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #66 | aliasing=auto, jsonb=json, field=direct, where=simple, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #67 | aliasing=auto, jsonb=json, field=direct, where=nested, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #68 | aliasing=auto, jsonb=json, field=direct, where=nested, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #69 | aliasing=auto, jsonb=json, field=direct, where=nested, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #70 | aliasing=auto, jsonb=json, field=direct, where=in, order_by=none
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #71 | aliasing=auto, jsonb=json, field=direct, where=in, order_by=single
SELECT "invoice_id" "expr0"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #72 | aliasing=auto, jsonb=json, field=direct, where=in, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #73 | aliasing=auto, jsonb=json, field=direct, where=between, order_by=none
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #74 | aliasing=auto, jsonb=json, field=direct, where=between, order_by=single
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #75 | aliasing=auto, jsonb=json, field=direct, where=between, order_by=multiple
SELECT "invoice_items"."invoice_id" "expr0"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #76 | aliasing=auto, jsonb=json, field=related, where=none, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id";

-- Test #77 | aliasing=auto, jsonb=json, field=related, where=none, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #78 | aliasing=auto, jsonb=json, field=related, where=none, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #79 | aliasing=auto, jsonb=json, field=related, where=simple, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10;

-- Test #80 | aliasing=auto, jsonb=json, field=related, where=simple, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #81 | aliasing=auto, jsonb=json, field=related, where=simple, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #82 | aliasing=auto, jsonb=json, field=related, where=nested, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100;

-- Test #83 | aliasing=auto, jsonb=json, field=related, where=nested, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #84 | aliasing=auto, jsonb=json, field=related, where=nested, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #85 | aliasing=auto, jsonb=json, field=related, where=in, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3);

-- Test #86 | aliasing=auto, jsonb=json, field=related, where=in, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #87 | aliasing=auto, jsonb=json, field=related, where=in, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #88 | aliasing=auto, jsonb=json, field=related, where=between, order_by=none
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #89 | aliasing=auto, jsonb=json, field=related, where=between, order_by=single
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #90 | aliasing=auto, jsonb=json, field=related, where=between, order_by=multiple
SELECT "customer__r"."customer_name" "expr0",
       "product__r"."product_name" "expr1",
       jsonb_build_object('customer__r', jsonb_build_object('expr0', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('expr1', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #91 | aliasing=auto, jsonb=json, field=aggregate, where=none, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #92 | aliasing=auto, jsonb=json, field=aggregate, where=none, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #93 | aliasing=auto, jsonb=json, field=aggregate, where=none, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #94 | aliasing=auto, jsonb=json, field=aggregate, where=simple, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #95 | aliasing=auto, jsonb=json, field=aggregate, where=simple, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #96 | aliasing=auto, jsonb=json, field=aggregate, where=simple, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #97 | aliasing=auto, jsonb=json, field=aggregate, where=nested, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #98 | aliasing=auto, jsonb=json, field=aggregate, where=nested, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #99 | aliasing=auto, jsonb=json, field=aggregate, where=nested, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #100 | aliasing=auto, jsonb=json, field=aggregate, where=in, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #101 | aliasing=auto, jsonb=json, field=aggregate, where=in, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #102 | aliasing=auto, jsonb=json, field=aggregate, where=in, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #103 | aliasing=auto, jsonb=json, field=aggregate, where=between, order_by=none
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #104 | aliasing=auto, jsonb=json, field=aggregate, where=between, order_by=single
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #105 | aliasing=auto, jsonb=json, field=aggregate, where=between, order_by=multiple
SELECT SUM("invoice_items"."quantity") "expr0",
       "invoice_items"."invoice_id" "expr1",
       "product__r"."product_name" "expr2",
       jsonb_build_object('expr2', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #106 | aliasing=auto, jsonb=json, field=expression, where=none, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items";

-- Test #107 | aliasing=auto, jsonb=json, field=expression, where=none, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #108 | aliasing=auto, jsonb=json, field=expression, where=none, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #109 | aliasing=auto, jsonb=json, field=expression, where=simple, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #110 | aliasing=auto, jsonb=json, field=expression, where=simple, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #111 | aliasing=auto, jsonb=json, field=expression, where=simple, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #112 | aliasing=auto, jsonb=json, field=expression, where=nested, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #113 | aliasing=auto, jsonb=json, field=expression, where=nested, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #114 | aliasing=auto, jsonb=json, field=expression, where=nested, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #115 | aliasing=auto, jsonb=json, field=expression, where=in, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #116 | aliasing=auto, jsonb=json, field=expression, where=in, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #117 | aliasing=auto, jsonb=json, field=expression, where=in, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #118 | aliasing=auto, jsonb=json, field=expression, where=between, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #119 | aliasing=auto, jsonb=json, field=expression, where=between, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #120 | aliasing=auto, jsonb=json, field=expression, where=between, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #121 | aliasing=none, jsonb=flat, field=direct, where=none, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items";

-- Test #122 | aliasing=none, jsonb=flat, field=direct, where=none, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #123 | aliasing=none, jsonb=flat, field=direct, where=none, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #124 | aliasing=none, jsonb=flat, field=direct, where=simple, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #125 | aliasing=none, jsonb=flat, field=direct, where=simple, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #126 | aliasing=none, jsonb=flat, field=direct, where=simple, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #127 | aliasing=none, jsonb=flat, field=direct, where=nested, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #128 | aliasing=none, jsonb=flat, field=direct, where=nested, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #129 | aliasing=none, jsonb=flat, field=direct, where=nested, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #130 | aliasing=none, jsonb=flat, field=direct, where=in, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #131 | aliasing=none, jsonb=flat, field=direct, where=in, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #132 | aliasing=none, jsonb=flat, field=direct, where=in, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #133 | aliasing=none, jsonb=flat, field=direct, where=between, order_by=none
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #134 | aliasing=none, jsonb=flat, field=direct, where=between, order_by=single
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #135 | aliasing=none, jsonb=flat, field=direct, where=between, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #136 | aliasing=none, jsonb=flat, field=related, where=none, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id";

-- Test #137 | aliasing=none, jsonb=flat, field=related, where=none, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #138 | aliasing=none, jsonb=flat, field=related, where=none, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #139 | aliasing=none, jsonb=flat, field=related, where=simple, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10;

-- Test #140 | aliasing=none, jsonb=flat, field=related, where=simple, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #141 | aliasing=none, jsonb=flat, field=related, where=simple, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #142 | aliasing=none, jsonb=flat, field=related, where=nested, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100;

-- Test #143 | aliasing=none, jsonb=flat, field=related, where=nested, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #144 | aliasing=none, jsonb=flat, field=related, where=nested, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #145 | aliasing=none, jsonb=flat, field=related, where=in, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3);

-- Test #146 | aliasing=none, jsonb=flat, field=related, where=in, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #147 | aliasing=none, jsonb=flat, field=related, where=in, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #148 | aliasing=none, jsonb=flat, field=related, where=between, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #149 | aliasing=none, jsonb=flat, field=related, where=between, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #150 | aliasing=none, jsonb=flat, field=related, where=between, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #151 | aliasing=none, jsonb=flat, field=aggregate, where=none, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #152 | aliasing=none, jsonb=flat, field=aggregate, where=none, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #153 | aliasing=none, jsonb=flat, field=aggregate, where=none, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #154 | aliasing=none, jsonb=flat, field=aggregate, where=simple, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #155 | aliasing=none, jsonb=flat, field=aggregate, where=simple, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #156 | aliasing=none, jsonb=flat, field=aggregate, where=simple, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #157 | aliasing=none, jsonb=flat, field=aggregate, where=nested, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #158 | aliasing=none, jsonb=flat, field=aggregate, where=nested, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #159 | aliasing=none, jsonb=flat, field=aggregate, where=nested, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #160 | aliasing=none, jsonb=flat, field=aggregate, where=in, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #161 | aliasing=none, jsonb=flat, field=aggregate, where=in, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #162 | aliasing=none, jsonb=flat, field=aggregate, where=in, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #163 | aliasing=none, jsonb=flat, field=aggregate, where=between, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #164 | aliasing=none, jsonb=flat, field=aggregate, where=between, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #165 | aliasing=none, jsonb=flat, field=aggregate, where=between, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #166 | aliasing=none, jsonb=flat, field=expression, where=none, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items";

-- Test #167 | aliasing=none, jsonb=flat, field=expression, where=none, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #168 | aliasing=none, jsonb=flat, field=expression, where=none, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #169 | aliasing=none, jsonb=flat, field=expression, where=simple, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #170 | aliasing=none, jsonb=flat, field=expression, where=simple, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #171 | aliasing=none, jsonb=flat, field=expression, where=simple, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #172 | aliasing=none, jsonb=flat, field=expression, where=nested, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #173 | aliasing=none, jsonb=flat, field=expression, where=nested, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #174 | aliasing=none, jsonb=flat, field=expression, where=nested, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #175 | aliasing=none, jsonb=flat, field=expression, where=in, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #176 | aliasing=none, jsonb=flat, field=expression, where=in, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #177 | aliasing=none, jsonb=flat, field=expression, where=in, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #178 | aliasing=none, jsonb=flat, field=expression, where=between, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #179 | aliasing=none, jsonb=flat, field=expression, where=between, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #180 | aliasing=none, jsonb=flat, field=expression, where=between, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #181 | aliasing=none, jsonb=json, field=direct, where=none, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items";

-- Test #182 | aliasing=none, jsonb=json, field=direct, where=none, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #183 | aliasing=none, jsonb=json, field=direct, where=none, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #184 | aliasing=none, jsonb=json, field=direct, where=simple, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #185 | aliasing=none, jsonb=json, field=direct, where=simple, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #186 | aliasing=none, jsonb=json, field=direct, where=simple, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #187 | aliasing=none, jsonb=json, field=direct, where=nested, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #188 | aliasing=none, jsonb=json, field=direct, where=nested, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #189 | aliasing=none, jsonb=json, field=direct, where=nested, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #190 | aliasing=none, jsonb=json, field=direct, where=in, order_by=none
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #191 | aliasing=none, jsonb=json, field=direct, where=in, order_by=single
SELECT "invoice_id" "invoice_id"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #192 | aliasing=none, jsonb=json, field=direct, where=in, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #193 | aliasing=none, jsonb=json, field=direct, where=between, order_by=none
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #194 | aliasing=none, jsonb=json, field=direct, where=between, order_by=single
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #195 | aliasing=none, jsonb=json, field=direct, where=between, order_by=multiple
SELECT "invoice_items"."invoice_id" "invoice_id"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #196 | aliasing=none, jsonb=json, field=related, where=none, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id";

-- Test #197 | aliasing=none, jsonb=json, field=related, where=none, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #198 | aliasing=none, jsonb=json, field=related, where=none, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #199 | aliasing=none, jsonb=json, field=related, where=simple, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10;

-- Test #200 | aliasing=none, jsonb=json, field=related, where=simple, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #201 | aliasing=none, jsonb=json, field=related, where=simple, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #202 | aliasing=none, jsonb=json, field=related, where=nested, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100;

-- Test #203 | aliasing=none, jsonb=json, field=related, where=nested, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #204 | aliasing=none, jsonb=json, field=related, where=nested, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #205 | aliasing=none, jsonb=json, field=related, where=in, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3);

-- Test #206 | aliasing=none, jsonb=json, field=related, where=in, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #207 | aliasing=none, jsonb=json, field=related, where=in, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #208 | aliasing=none, jsonb=json, field=related, where=between, order_by=none
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #209 | aliasing=none, jsonb=json, field=related, where=between, order_by=single
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #210 | aliasing=none, jsonb=json, field=related, where=between, order_by=multiple
SELECT "customer__r"."customer_name" "customer_name",
       "product__r"."product_name" "product_name",
       jsonb_build_object('customer__r', jsonb_build_object('customer_name', "customer__r"."customer_name")) "invoice__r",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "customers" "customer__r" ON "invoice__r"."customer_id"="customer__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #211 | aliasing=none, jsonb=json, field=aggregate, where=none, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #212 | aliasing=none, jsonb=json, field=aggregate, where=none, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #213 | aliasing=none, jsonb=json, field=aggregate, where=none, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #214 | aliasing=none, jsonb=json, field=aggregate, where=simple, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #215 | aliasing=none, jsonb=json, field=aggregate, where=simple, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #216 | aliasing=none, jsonb=json, field=aggregate, where=simple, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #217 | aliasing=none, jsonb=json, field=aggregate, where=nested, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #218 | aliasing=none, jsonb=json, field=aggregate, where=nested, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #219 | aliasing=none, jsonb=json, field=aggregate, where=nested, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #220 | aliasing=none, jsonb=json, field=aggregate, where=in, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #221 | aliasing=none, jsonb=json, field=aggregate, where=in, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #222 | aliasing=none, jsonb=json, field=aggregate, where=in, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #223 | aliasing=none, jsonb=json, field=aggregate, where=between, order_by=none
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id";

-- Test #224 | aliasing=none, jsonb=json, field=aggregate, where=between, order_by=single
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #225 | aliasing=none, jsonb=json, field=aggregate, where=between, order_by=multiple
SELECT SUM("invoice_items"."quantity") "quantity_sum",
       "invoice_items"."invoice_id" "invoice_id",
       "product__r"."product_name" "product_name",
       jsonb_build_object('product_name', "product__r"."product_name") "product__r"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
GROUP BY "product__r"."product_name",
         "invoice_items"."invoice_id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #226 | aliasing=none, jsonb=json, field=expression, where=none, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items";

-- Test #227 | aliasing=none, jsonb=json, field=expression, where=none, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
ORDER BY "invoice_id" DESC;

-- Test #228 | aliasing=none, jsonb=json, field=expression, where=none, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #229 | aliasing=none, jsonb=json, field=expression, where=simple, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10;

-- Test #230 | aliasing=none, jsonb=json, field=expression, where=simple, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">10
ORDER BY "invoice_id" DESC;

-- Test #231 | aliasing=none, jsonb=json, field=expression, where=simple, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">10
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #232 | aliasing=none, jsonb=json, field=expression, where=nested, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100;

-- Test #233 | aliasing=none, jsonb=json, field=expression, where=nested, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "quantity">5
  AND "unit_price"<100
ORDER BY "invoice_id" DESC;

-- Test #234 | aliasing=none, jsonb=json, field=expression, where=nested, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."quantity">5
  AND "invoice_items"."unit_price"<100
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #235 | aliasing=none, jsonb=json, field=expression, where=in, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3);

-- Test #236 | aliasing=none, jsonb=json, field=expression, where=in, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
WHERE "invoice_id" IN (1,
                       2,
                       3)
ORDER BY "invoice_id" DESC;

-- Test #237 | aliasing=none, jsonb=json, field=expression, where=in, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice_items"."invoice_id" IN (1,
                                       2,
                                       3)
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

-- Test #238 | aliasing=none, jsonb=json, field=expression, where=between, order_by=none
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31';

-- Test #239 | aliasing=none, jsonb=json, field=expression, where=between, order_by=single
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC;

-- Test #240 | aliasing=none, jsonb=json, field=expression, where=between, order_by=multiple
SELECT ('quantity * unit_price') "total_value"
FROM "invoice_items"
LEFT JOIN "invoices" "invoice__r" ON "invoice_items"."invoice_id"="invoice__r"."id"
LEFT JOIN "products" "product__r" ON "invoice_items"."product_id"="product__r"."id"
WHERE "invoice__r"."invoice_date" BETWEEN '2023-01-01' AND '2023-12-31'
ORDER BY "invoice_items"."invoice_id" DESC,
         "product__r"."product_name" ASC;

