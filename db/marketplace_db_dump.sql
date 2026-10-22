--
-- PostgreSQL database dump
--

\restrict iipnq9MqOqEV01qNzRblbqpfGZq2aOm7WOyc5vbyRl6a5wwga3BeQuKmzfofi2s

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

-- Started on 2026-10-22 21:38:39

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 226 (class 1259 OID 24971)
-- Name: price_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.price_history (
    id bigint NOT NULL,
    product_id bigint NOT NULL,
    run_id bigint NOT NULL,
    observed_at timestamp with time zone DEFAULT now() NOT NULL,
    price numeric(14,2),
    currency character(3) DEFAULT 'RUB'::bpchar NOT NULL,
    region text DEFAULT 'unknown'::text NOT NULL,
    price_kind text DEFAULT 'unknown'::text NOT NULL,
    availability text DEFAULT 'unknown'::text NOT NULL,
    rating numeric(3,2),
    reviews_count integer,
    CONSTRAINT price_history_availability_check CHECK ((availability = ANY (ARRAY['in_stock'::text, 'out_of_stock'::text, 'unknown'::text]))),
    CONSTRAINT price_history_price_check CHECK ((price >= (0)::numeric)),
    CONSTRAINT price_history_price_kind_check CHECK ((price_kind = ANY (ARRAY['regular'::text, 'card'::text, 'subscription'::text, 'unknown'::text]))),
    CONSTRAINT price_history_rating_check CHECK (((rating >= (0)::numeric) AND (rating <= (5)::numeric))),
    CONSTRAINT price_history_reviews_count_check CHECK ((reviews_count >= 0))
);


--
-- TOC entry 227 (class 1259 OID 25014)
-- Name: current_prices; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.current_prices AS
 SELECT DISTINCT ON (product_id, region, currency, price_kind) id,
    product_id,
    run_id,
    observed_at,
    price,
    currency,
    region,
    price_kind,
    availability,
    rating,
    reviews_count
   FROM public.price_history
  ORDER BY product_id, region, currency, price_kind, observed_at DESC, id DESC;


--
-- TOC entry 220 (class 1259 OID 24914)
-- Name: marketplaces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.marketplaces (
    id bigint NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(100) NOT NULL
);


--
-- TOC entry 219 (class 1259 OID 24913)
-- Name: marketplaces_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.marketplaces ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.marketplaces_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 224 (class 1259 OID 24950)
-- Name: parse_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parse_runs (
    id bigint NOT NULL,
    marketplace_id bigint NOT NULL,
    source_url text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    error_message text,
    CONSTRAINT parse_runs_status_check CHECK ((status = ANY (ARRAY['running'::text, 'succeeded'::text, 'failed'::text])))
);


--
-- TOC entry 223 (class 1259 OID 24949)
-- Name: parse_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.parse_runs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.parse_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 225 (class 1259 OID 24970)
-- Name: price_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.price_history ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.price_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 222 (class 1259 OID 24925)
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id bigint NOT NULL,
    marketplace_id bigint NOT NULL,
    external_id text NOT NULL,
    name text NOT NULL,
    url text,
    brand text,
    model text,
    connection_type text,
    form_factor text,
    anc boolean,
    microphone boolean,
    battery_hours numeric(4,1),
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT products_connection_type_check CHECK ((connection_type = ANY (ARRAY['wired'::text, 'bluetooth'::text, 'radio'::text]))),
    CONSTRAINT products_form_factor_check CHECK ((form_factor = ANY (ARRAY['in_ear'::text, 'on_ear'::text, 'over_ear'::text])))
);


--
-- TOC entry 221 (class 1259 OID 24924)
-- Name: products_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.products ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 4964 (class 0 OID 24914)
-- Dependencies: 220
-- Data for Name: marketplaces; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.marketplaces (id, code, name) FROM stdin;
1	wb	Wildberries
2	ozon	Ozon
5	ym	Яндекс Маркет
\.


--
-- TOC entry 4968 (class 0 OID 24950)
-- Dependencies: 224
-- Data for Name: parse_runs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.parse_runs (id, marketplace_id, source_url, started_at, finished_at, status, error_message) FROM stdin;
4	1	https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%BD%D0%B0%D1%83%D1%88%D0%BD%D0%B8%D0%BA%D0%B8	2026-10-19 01:57:54.924758+03	2026-10-19 01:58:34.437091+03	succeeded	\N
5	1	https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%BD%D0%B0%D1%83%D1%88%D0%BD%D0%B8%D0%BA%D0%B8	2026-10-21 15:11:46.476777+03	2026-10-21 15:16:06.978904+03	succeeded	\N
6	1	https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%BD%D0%B0%D1%83%D1%88%D0%BD%D0%B8%D0%BA%D0%B8	2026-10-21 16:27:36.866785+03	2026-10-21 16:34:02.588159+03	succeeded	\N
7	1	https://www.wildberries.ru/catalog/0/search.aspx?search=%D0%BD%D0%B0%D1%83%D1%88%D0%BD%D0%B8%D0%BA%D0%B8	2026-10-21 16:44:20.21994+03	2026-10-21 16:50:39.634836+03	succeeded	\N
8	2	import:products_ozon.json	2026-10-21 18:14:17.48126+03	2026-10-21 18:14:17.516792+03	succeeded	\N
9	2	import:products_ozon (1).json	2026-10-21 18:14:32.362521+03	2026-10-21 18:14:32.405166+03	succeeded	\N
\.


--
-- TOC entry 4970 (class 0 OID 24971)
-- Dependencies: 226
-- Data for Name: price_history; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.price_history (id, product_id, run_id, observed_at, price, currency, region, price_kind, availability, rating, reviews_count) FROM stdin;
3	1	4	2026-10-19 01:58:13.430158+03	582.00	RUB	unknown	unknown	unknown	4.80	9974
4	2	4	2026-10-19 01:58:21.427731+03	2562.00	RUB	unknown	unknown	unknown	4.80	3201
5	3	4	2026-10-19 01:58:30.203008+03	1068.00	RUB	unknown	unknown	unknown	4.80	2736
6	5	5	2026-10-21 15:12:09.1931+03	4570.00	RUB	unknown	unknown	unknown	4.90	1
7	6	5	2026-10-21 15:12:17.152558+03	2482.00	RUB	unknown	unknown	unknown	4.90	252
8	1	5	2026-10-21 15:12:25.004729+03	579.00	RUB	unknown	unknown	unknown	4.80	10109
9	8	5	2026-10-21 15:12:32.988768+03	1478.00	RUB	unknown	unknown	unknown	4.80	12316
10	9	5	2026-10-21 15:12:40.833023+03	2395.00	RUB	unknown	unknown	unknown	4.80	3750
11	10	5	2026-10-21 15:12:48.647898+03	14847.00	RUB	unknown	unknown	unknown	4.70	203
12	11	5	2026-10-21 15:12:56.540029+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
13	12	5	2026-10-21 15:13:04.114268+03	1520.00	RUB	unknown	unknown	unknown	5.00	15194
14	13	5	2026-10-21 15:13:11.912142+03	2400.00	RUB	unknown	unknown	unknown	4.90	8
15	14	5	2026-10-21 15:13:19.74164+03	1635.00	RUB	unknown	unknown	unknown	4.80	52
16	15	5	2026-10-21 15:13:27.56635+03	870.00	RUB	unknown	unknown	unknown	4.80	261
17	16	5	2026-10-21 15:13:35.14428+03	3182.00	RUB	unknown	unknown	unknown	4.90	2
18	17	5	2026-10-21 15:13:43.824775+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
19	18	5	2026-10-21 15:13:51.639846+03	468.00	RUB	unknown	unknown	unknown	4.70	\N
20	19	5	2026-10-21 15:14:00.21721+03	1933.00	RUB	unknown	unknown	unknown	4.50	516
21	20	5	2026-10-21 15:14:07.93931+03	2070.00	RUB	unknown	unknown	unknown	4.90	4413
22	21	5	2026-10-21 15:14:16.094288+03	2622.00	RUB	unknown	unknown	unknown	4.90	320
23	22	5	2026-10-21 15:14:23.951151+03	1379.00	RUB	unknown	unknown	unknown	4.70	4043
24	23	5	2026-10-21 15:14:31.764328+03	2714.00	RUB	unknown	unknown	unknown	4.90	255
25	24	5	2026-10-21 15:14:39.499849+03	1568.00	RUB	unknown	unknown	unknown	4.70	12981
26	25	5	2026-10-21 15:14:47.316708+03	1636.00	RUB	unknown	unknown	unknown	4.70	84
27	26	5	2026-10-21 15:14:55.908806+03	2922.00	RUB	unknown	unknown	unknown	4.30	6
28	27	5	2026-10-21 15:15:04.12242+03	1729.00	RUB	unknown	unknown	unknown	4.70	62
29	28	5	2026-10-21 15:15:12.326248+03	1029.00	RUB	unknown	unknown	unknown	4.90	59940
30	29	5	2026-10-21 15:15:20.193887+03	7514.00	RUB	unknown	unknown	unknown	4.90	\N
31	30	5	2026-10-21 15:15:28.893525+03	1487.00	RUB	unknown	unknown	unknown	4.80	12316
32	31	5	2026-10-21 15:15:36.457951+03	1598.00	RUB	unknown	unknown	unknown	4.70	384
33	32	5	2026-10-21 15:15:44.372033+03	2993.00	RUB	unknown	unknown	unknown	4.80	898
34	33	5	2026-10-21 15:15:52.773708+03	10630.00	RUB	unknown	unknown	unknown	\N	\N
35	34	5	2026-10-21 15:16:01.39005+03	1353.00	RUB	unknown	unknown	unknown	4.70	761
36	5	6	2026-10-21 16:28:01.58256+03	4570.00	RUB	unknown	unknown	unknown	4.90	1
37	1	6	2026-10-21 16:28:13.598586+03	579.00	RUB	unknown	unknown	unknown	4.80	10109
38	37	6	2026-10-21 16:28:25.57435+03	14892.00	RUB	unknown	unknown	unknown	4.90	1
39	8	6	2026-10-21 16:28:38.469241+03	1478.00	RUB	unknown	unknown	unknown	4.80	12316
40	9	6	2026-10-21 16:28:50.321968+03	2395.00	RUB	unknown	unknown	unknown	4.80	3750
41	40	6	2026-10-21 16:29:03.054234+03	2102.00	RUB	unknown	unknown	unknown	4.90	1090
42	10	6	2026-10-21 16:29:15.165737+03	14847.00	RUB	unknown	unknown	unknown	4.70	203
43	11	6	2026-10-21 16:29:27.133877+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
44	43	6	2026-10-21 16:29:39.591203+03	783.00	RUB	unknown	unknown	unknown	4.80	121
45	12	6	2026-10-21 16:29:52.099317+03	1520.00	RUB	unknown	unknown	unknown	5.00	15194
46	13	6	2026-10-21 16:30:04.35118+03	2400.00	RUB	unknown	unknown	unknown	4.90	8
47	46	6	2026-10-21 16:30:16.882472+03	664.00	RUB	unknown	unknown	unknown	4.80	937
48	14	6	2026-10-21 16:30:29.58475+03	1635.00	RUB	unknown	unknown	unknown	4.80	52
49	48	6	2026-10-21 16:30:41.580203+03	1992.00	RUB	unknown	unknown	unknown	4.90	155
50	49	6	2026-10-21 16:30:53.330749+03	1956.00	RUB	unknown	unknown	unknown	4.70	225
51	16	6	2026-10-21 16:31:05.256385+03	3182.00	RUB	unknown	unknown	unknown	4.90	2
52	17	6	2026-10-21 16:31:20.155139+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
53	52	6	2026-10-21 16:31:32.163837+03	485.00	RUB	unknown	unknown	unknown	4.80	11227
54	18	6	2026-10-21 16:31:44.451326+03	468.00	RUB	unknown	unknown	unknown	4.70	\N
55	54	6	2026-10-21 16:31:56.130049+03	9069.00	RUB	unknown	unknown	unknown	4.60	1
56	20	6	2026-10-21 16:32:08.816715+03	2070.00	RUB	unknown	unknown	unknown	4.90	4413
57	21	6	2026-10-21 16:32:21.165309+03	2622.00	RUB	unknown	unknown	unknown	4.90	320
58	22	6	2026-10-21 16:32:33.884223+03	1379.00	RUB	unknown	unknown	unknown	4.70	4043
59	23	6	2026-10-21 16:32:45.820986+03	2714.00	RUB	unknown	unknown	unknown	4.90	255
60	59	6	2026-10-21 16:32:57.541788+03	355.00	RUB	unknown	unknown	unknown	4.70	4903
61	60	6	2026-10-21 16:33:09.56032+03	1501.00	RUB	unknown	unknown	unknown	4.70	7154
62	25	6	2026-10-21 16:33:21.601679+03	1636.00	RUB	unknown	unknown	unknown	4.70	84
63	26	6	2026-10-21 16:33:34.301555+03	2922.00	RUB	unknown	unknown	unknown	4.30	6
64	27	6	2026-10-21 16:33:46.625201+03	1729.00	RUB	unknown	unknown	unknown	4.70	62
65	28	6	2026-10-21 16:33:58.332473+03	1029.00	RUB	unknown	unknown	unknown	4.90	59940
66	5	7	2026-10-21 16:44:44.434302+03	9633.00	RUB	unknown	unknown	unknown	4.90	1
67	1	7	2026-10-21 16:44:56.421154+03	579.00	RUB	unknown	unknown	unknown	4.80	10109
68	37	7	2026-10-21 16:45:09.190663+03	14892.00	RUB	unknown	unknown	unknown	4.90	1
69	8	7	2026-10-21 16:45:20.929026+03	1478.00	RUB	unknown	unknown	unknown	4.80	12316
70	9	7	2026-10-21 16:45:32.941085+03	2395.00	RUB	unknown	unknown	unknown	4.80	3750
71	40	7	2026-10-21 16:45:45.550641+03	2102.00	RUB	unknown	unknown	unknown	4.90	1090
72	10	7	2026-10-21 16:45:57.536422+03	14847.00	RUB	unknown	unknown	unknown	4.70	203
73	11	7	2026-10-21 16:46:10.362878+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
74	12	7	2026-10-21 16:46:22.025453+03	1520.00	RUB	unknown	unknown	unknown	5.00	15194
75	13	7	2026-10-21 16:46:33.927595+03	2400.00	RUB	unknown	unknown	unknown	4.90	8
76	46	7	2026-10-21 16:46:45.941403+03	664.00	RUB	unknown	unknown	unknown	4.80	937
77	14	7	2026-10-21 16:46:57.877611+03	1635.00	RUB	unknown	unknown	unknown	4.80	52
78	48	7	2026-10-21 16:47:10.512852+03	1992.00	RUB	unknown	unknown	unknown	4.90	155
79	49	7	2026-10-21 16:47:22.225838+03	1956.00	RUB	unknown	unknown	unknown	4.70	225
80	16	7	2026-10-21 16:47:34.133785+03	3182.00	RUB	unknown	unknown	unknown	4.90	2
81	17	7	2026-10-21 16:47:46.065366+03	1493.00	RUB	unknown	unknown	unknown	4.70	12981
82	18	7	2026-10-21 16:47:57.760538+03	468.00	RUB	unknown	unknown	unknown	4.70	\N
83	19	7	2026-10-21 16:48:09.657034+03	1933.00	RUB	unknown	unknown	unknown	4.50	516
84	54	7	2026-10-21 16:48:22.228466+03	9069.00	RUB	unknown	unknown	unknown	4.60	1
85	20	7	2026-10-21 16:48:34.168183+03	2070.00	RUB	unknown	unknown	unknown	4.90	4413
86	21	7	2026-10-21 16:48:46.392256+03	2622.00	RUB	unknown	unknown	unknown	4.90	320
87	22	7	2026-10-21 16:48:59.001501+03	1379.00	RUB	unknown	unknown	unknown	4.70	4043
88	23	7	2026-10-21 16:49:11.249355+03	2714.00	RUB	unknown	unknown	unknown	4.90	255
89	60	7	2026-10-21 16:49:23.367505+03	1501.00	RUB	unknown	unknown	unknown	4.70	7154
90	25	7	2026-10-21 16:49:35.275001+03	1636.00	RUB	unknown	unknown	unknown	4.70	84
91	26	7	2026-10-21 16:49:47.171427+03	2922.00	RUB	unknown	unknown	unknown	4.30	6
92	27	7	2026-10-21 16:49:58.863368+03	1729.00	RUB	unknown	unknown	unknown	4.70	62
93	28	7	2026-10-21 16:50:11.101021+03	1029.00	RUB	unknown	unknown	unknown	4.90	59940
94	93	7	2026-10-21 16:50:23.432091+03	40520.00	RUB	unknown	unknown	unknown	4.70	6
95	30	7	2026-10-21 16:50:35.362856+03	1487.00	RUB	unknown	unknown	unknown	4.80	12316
96	95	8	2026-10-21 18:14:17.48937+03	2218.00	RUB	unknown	unknown	unknown	\N	\N
97	96	8	2026-10-21 18:14:17.500509+03	2855.00	RUB	unknown	unknown	unknown	\N	\N
98	97	8	2026-10-21 18:14:17.502021+03	3959.00	RUB	unknown	unknown	unknown	\N	\N
99	98	8	2026-10-21 18:14:17.502914+03	1414.00	RUB	unknown	unknown	unknown	\N	\N
100	99	8	2026-10-21 18:14:17.503744+03	2439.00	RUB	unknown	unknown	unknown	\N	\N
101	100	8	2026-10-21 18:14:17.504607+03	6591.00	RUB	unknown	unknown	unknown	\N	\N
102	101	8	2026-10-21 18:14:17.505706+03	2332.00	RUB	unknown	unknown	unknown	\N	\N
103	102	8	2026-10-21 18:14:17.506962+03	6590.00	RUB	unknown	unknown	unknown	\N	\N
104	103	8	2026-10-21 18:14:17.507609+03	3112.00	RUB	unknown	unknown	unknown	\N	\N
105	104	8	2026-10-21 18:14:17.508187+03	1794.00	RUB	unknown	unknown	unknown	\N	\N
106	105	8	2026-10-21 18:14:17.508949+03	1970.00	RUB	unknown	unknown	unknown	\N	\N
107	106	8	2026-10-21 18:14:17.509642+03	4742.00	RUB	unknown	unknown	unknown	\N	\N
108	107	8	2026-10-21 18:14:17.510321+03	16820.00	RUB	unknown	unknown	unknown	\N	\N
109	108	8	2026-10-21 18:14:17.511259+03	1277.00	RUB	unknown	unknown	unknown	\N	\N
110	109	8	2026-10-21 18:14:17.512297+03	1664.00	RUB	unknown	unknown	unknown	\N	\N
111	110	8	2026-10-21 18:14:17.513714+03	18403.00	RUB	unknown	unknown	unknown	\N	\N
112	111	8	2026-10-21 18:14:17.514574+03	4515.00	RUB	unknown	unknown	unknown	\N	\N
113	112	8	2026-10-21 18:14:17.515383+03	3959.00	RUB	unknown	unknown	unknown	\N	\N
114	113	8	2026-10-21 18:14:17.516158+03	1375.00	RUB	unknown	unknown	unknown	\N	\N
115	114	9	2026-10-21 18:14:32.368323+03	609.00	RUB	unknown	unknown	unknown	\N	\N
116	115	9	2026-10-21 18:14:32.373359+03	3208.00	RUB	unknown	unknown	unknown	\N	\N
117	116	9	2026-10-21 18:14:32.374375+03	1507.00	RUB	unknown	unknown	unknown	\N	\N
118	117	9	2026-10-21 18:14:32.37516+03	4704.00	RUB	unknown	unknown	unknown	\N	\N
119	95	9	2026-10-21 18:14:32.375838+03	2218.00	RUB	unknown	unknown	unknown	\N	\N
120	119	9	2026-10-21 18:14:32.376486+03	1633.00	RUB	unknown	unknown	unknown	\N	\N
121	120	9	2026-10-21 18:14:32.377239+03	1654.00	RUB	unknown	unknown	unknown	\N	\N
122	121	9	2026-10-21 18:14:32.377985+03	359.00	RUB	unknown	unknown	unknown	\N	\N
123	122	9	2026-10-21 18:14:32.378577+03	7548.00	RUB	unknown	unknown	unknown	\N	\N
124	123	9	2026-10-21 18:14:32.379149+03	980.00	RUB	unknown	unknown	unknown	\N	\N
125	124	9	2026-10-21 18:14:32.379716+03	5246.00	RUB	unknown	unknown	unknown	\N	\N
126	125	9	2026-10-21 18:14:32.380279+03	3333.00	RUB	unknown	unknown	unknown	\N	\N
127	126	9	2026-10-21 18:14:32.380867+03	1395.00	RUB	unknown	unknown	unknown	\N	\N
128	127	9	2026-10-21 18:14:32.381438+03	1524.00	RUB	unknown	unknown	unknown	\N	\N
129	128	9	2026-10-21 18:14:32.3821+03	1719.00	RUB	unknown	unknown	unknown	\N	\N
130	129	9	2026-10-21 18:14:32.382833+03	1895.00	RUB	unknown	unknown	unknown	\N	\N
131	130	9	2026-10-21 18:14:32.383567+03	11392.00	RUB	unknown	unknown	unknown	\N	\N
132	131	9	2026-10-21 18:14:32.384228+03	4488.00	RUB	unknown	unknown	unknown	\N	\N
133	132	9	2026-10-21 18:14:32.384879+03	2134.00	RUB	unknown	unknown	unknown	\N	\N
134	133	9	2026-10-21 18:14:32.385456+03	508.00	RUB	unknown	unknown	unknown	\N	\N
135	134	9	2026-10-21 18:14:32.386011+03	2233.00	RUB	unknown	unknown	unknown	\N	\N
136	135	9	2026-10-21 18:14:32.386559+03	1277.00	RUB	unknown	unknown	unknown	\N	\N
137	136	9	2026-10-21 18:14:32.387141+03	1028.00	RUB	unknown	unknown	unknown	\N	\N
138	137	9	2026-10-21 18:14:32.387721+03	2434.00	RUB	unknown	unknown	unknown	\N	\N
139	138	9	2026-10-21 18:14:32.388275+03	483.00	RUB	unknown	unknown	unknown	\N	\N
140	139	9	2026-10-21 18:14:32.388889+03	5731.00	RUB	unknown	unknown	unknown	\N	\N
141	140	9	2026-10-21 18:14:32.389437+03	4058.00	RUB	unknown	unknown	unknown	\N	\N
142	141	9	2026-10-21 18:14:32.39+03	2470.00	RUB	unknown	unknown	unknown	\N	\N
143	142	9	2026-10-21 18:14:32.39149+03	1991.00	RUB	unknown	unknown	unknown	\N	\N
144	143	9	2026-10-21 18:14:32.39215+03	3293.00	RUB	unknown	unknown	unknown	\N	\N
145	144	9	2026-10-21 18:14:32.392831+03	5543.00	RUB	unknown	unknown	unknown	\N	\N
146	145	9	2026-10-21 18:14:32.393419+03	3490.00	RUB	unknown	unknown	unknown	\N	\N
147	146	9	2026-10-21 18:14:32.394+03	1767.00	RUB	unknown	unknown	unknown	\N	\N
148	147	9	2026-10-21 18:14:32.394555+03	3563.00	RUB	unknown	unknown	unknown	\N	\N
149	148	9	2026-10-21 18:14:32.395099+03	11870.00	RUB	unknown	unknown	unknown	\N	\N
150	149	9	2026-10-21 18:14:32.395684+03	2817.00	RUB	unknown	unknown	unknown	\N	\N
151	150	9	2026-10-21 18:14:32.396303+03	734.00	RUB	unknown	unknown	unknown	\N	\N
152	151	9	2026-10-21 18:14:32.39688+03	2514.00	RUB	unknown	unknown	unknown	\N	\N
153	152	9	2026-10-21 18:14:32.397477+03	1866.00	RUB	unknown	unknown	unknown	\N	\N
154	153	9	2026-10-21 18:14:32.398135+03	1121.00	RUB	unknown	unknown	unknown	\N	\N
155	154	9	2026-10-21 18:14:32.398686+03	1277.00	RUB	unknown	unknown	unknown	\N	\N
156	155	9	2026-10-21 18:14:32.399232+03	1910.00	RUB	unknown	unknown	unknown	\N	\N
157	156	9	2026-10-21 18:14:32.399774+03	2069.00	RUB	unknown	unknown	unknown	\N	\N
158	157	9	2026-10-21 18:14:32.400332+03	843.00	RUB	unknown	unknown	unknown	\N	\N
159	158	9	2026-10-21 18:14:32.400871+03	2189.00	RUB	unknown	unknown	unknown	\N	\N
160	159	9	2026-10-21 18:14:32.40343+03	515.00	RUB	unknown	unknown	unknown	\N	\N
161	160	9	2026-10-21 18:14:32.404093+03	1106.00	RUB	unknown	unknown	unknown	\N	\N
162	161	9	2026-10-21 18:14:32.404655+03	4058.00	RUB	unknown	unknown	unknown	\N	\N
\.


--
-- TOC entry 4966 (class 0 OID 24925)
-- Dependencies: 222
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.products (id, marketplace_id, external_id, name, url, brand, model, connection_type, form_factor, anc, microphone, battery_hours, first_seen_at, last_seen_at) FROM stdin;
2	1	1534125592	Беспроводные наушники для телефона сердечки для девочки	https://www.wildberries.ru/catalog/1534125592/detail.aspx	ZESTIFY	\N	bluetooth	\N	\N	\N	\N	2026-10-19 01:58:21.427731+03	2026-10-19 01:58:21.427731+03
3	1	419893789	Наушники беспроводные для андроид и iPhone	https://www.wildberries.ru/catalog/419893789/detail.aspx	MOBIKAS	\N	bluetooth	\N	\N	\N	\N	2026-10-19 01:58:30.203008+03	2026-10-19 01:58:30.203008+03
1	1	1560826374	Наушники беспроводные Pro	https://www.wildberries.ru/catalog/1560826374/detail.aspx	\N	\N	bluetooth	in_ear	\N	t	4.0	2026-10-19 01:58:13.430158+03	2026-10-21 16:44:56.421154+03
6	1	502778882	Наушники беспроводные FreeBuds SE 2 Фиолетовый	https://www.wildberries.ru/catalog/502778882/detail.aspx	Huawei	\N	bluetooth	\N	\N	\N	\N	2026-10-21 15:12:17.152558+03	2026-10-21 15:12:17.152558+03
15	1	48870964	Блютуз наушники беспроводные большие накладные с микрофоном	https://www.wildberries.ru/catalog/48870964/detail.aspx	Harper	\N	bluetooth	on_ear	\N	t	\N	2026-10-21 15:13:27.56635+03	2026-10-21 15:13:27.56635+03
24	1	543342149	Наушники беспроводные с микрофоном для андроид и iphone	https://www.wildberries.ru/catalog/543342149/detail.aspx	Todosound	\N	bluetooth	\N	\N	t	\N	2026-10-21 15:14:39.499849+03	2026-10-21 15:14:39.499849+03
29	1	1721428580	Беспроводные наушники FreeBuds Neo Космический черный	https://www.wildberries.ru/catalog/1721428580/detail.aspx	Huawei	\N	bluetooth	\N	\N	\N	\N	2026-10-21 15:15:20.193887+03	2026-10-21 15:15:20.193887+03
31	1	765437543	Наушники беспроводные BP1 NC с шумоподавлением, белые	https://www.wildberries.ru/catalog/765437543/detail.aspx	Baseus	\N	bluetooth	\N	t	\N	\N	2026-10-21 15:15:36.457951+03	2026-10-21 15:15:36.457951+03
32	1	1282279530	Наушники беспроводные с шумоподавлением и микрофоном	https://www.wildberries.ru/catalog/1282279530/detail.aspx	Samsung	\N	bluetooth	\N	\N	t	\N	2026-10-21 15:15:44.372033+03	2026-10-21 15:15:44.372033+03
33	1	1878653039	Наушники FreeClip 2 Berry Purple	https://www.wildberries.ru/catalog/1878653039/detail.aspx	Huawei	\N	\N	\N	\N	\N	\N	2026-10-21 15:15:52.773708+03	2026-10-21 15:15:52.773708+03
34	1	600964207	Беспроводные накладные наушники большие W35	https://www.wildberries.ru/catalog/600964207/detail.aspx	HOCO	\N	bluetooth	on_ear	\N	\N	\N	2026-10-21 15:16:01.39005+03	2026-10-21 15:16:01.39005+03
43	1	141393439	Наушники беспроводные с микрофоном спортивные стерео	https://www.wildberries.ru/catalog/141393439/detail.aspx	Earldom	\N	bluetooth	in_ear	t	t	25.0	2026-10-21 16:29:39.591203+03	2026-10-21 16:29:39.591203+03
14	1	1580746790	Наушники-клипсы беспроводные с AI-переводчиком, до 48 ч	https://www.wildberries.ru/catalog/1580746790/detail.aspx	\N	\N	bluetooth	\N	\N	t	48.0	2026-10-21 15:13:19.74164+03	2026-10-21 16:46:57.877611+03
16	1	622418486	Беспроводные наушники CMF by Nothing Buds 2a темно-серый	https://www.wildberries.ru/catalog/622418486/detail.aspx	Nothing	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 15:13:35.14428+03	2026-10-21 16:47:34.133785+03
19	1	413659195	Наушники беспроводные AirPods 4 ANC для iPhone и Android	https://www.wildberries.ru/catalog/413659195/detail.aspx	\N	\N	bluetooth	\N	t	\N	30.0	2026-10-21 15:14:00.21721+03	2026-10-21 16:48:09.657034+03
21	1	366644286	Беспроводные наушники FreeBuds SE 2, белые	https://www.wildberries.ru/catalog/366644286/detail.aspx	Huawei	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 15:14:16.094288+03	2026-10-21 16:48:46.392256+03
27	1	599396444	Наушники беспроводные Airpods Pro 3 для iPhone Android	https://www.wildberries.ru/catalog/599396444/detail.aspx	IQUANT	\N	wired	in_ear	\N	t	\N	2026-10-21 15:15:04.12242+03	2026-10-21 16:49:58.863368+03
5	1	622418432	Беспроводные наушники CMF by Nothing Buds Pro 2 синий	https://www.wildberries.ru/catalog/622418432/detail.aspx	Nothing	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 15:12:09.1931+03	2026-10-21 16:44:44.434302+03
37	1	1309040136	Наушники беспроводные FreeClip 2 S Глубокий синий	https://www.wildberries.ru/catalog/1309040136/detail.aspx	Huawei	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 16:28:25.57435+03	2026-10-21 16:45:09.190663+03
8	1	332357129	Наушники беспроводные для андроид и iphone	https://www.wildberries.ru/catalog/332357129/detail.aspx	ZIMI	\N	bluetooth	in_ear	t	t	150.0	2026-10-21 15:12:32.988768+03	2026-10-21 16:45:20.929026+03
9	1	166127630	Наушники проводные большие с микрофоном Studio Pro 10	https://www.wildberries.ru/catalog/166127630/detail.aspx	\N	\N	wired	on_ear	\N	t	\N	2026-10-21 15:12:40.833023+03	2026-10-21 16:45:32.941085+03
40	1	263578638	Наушники беспроводные большие с шумоподавлением	https://www.wildberries.ru/catalog/263578638/detail.aspx	Maxper	\N	bluetooth	over_ear	t	\N	60.0	2026-10-21 16:29:03.054234+03	2026-10-21 16:45:45.550641+03
10	1	551514647	Наушники игровые беспроводные с микрофоном G PRO X 2 lightspeed	https://www.wildberries.ru/catalog/551514647/detail.aspx	LOGITECH	\N	radio	over_ear	\N	t	50.0	2026-10-21 15:12:48.647898+03	2026-10-21 16:45:57.536422+03
11	1	920760862	Наушники беспроводные с микрофоном для андроид и iphone	https://www.wildberries.ru/catalog/920760862/detail.aspx	Todosound	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 15:12:56.540029+03	2026-10-21 16:46:10.362878+03
12	1	1556435490	Беспроводные Bluetooth наушники для iPhone и Android	https://www.wildberries.ru/catalog/1556435490/detail.aspx	\N	\N	bluetooth	in_ear	\N	t	30.0	2026-10-21 15:13:04.114268+03	2026-10-21 16:46:22.025453+03
13	1	984342563	Беспроводная гарнитура Earbuds S7,белое	https://www.wildberries.ru/catalog/984342563/detail.aspx	HONOR	\N	bluetooth	\N	\N	\N	\N	2026-10-21 15:13:11.912142+03	2026-10-21 16:46:33.927595+03
17	1	924385335	Наушники беспроводные с микрофоном для андроид и iphone	https://www.wildberries.ru/catalog/924385335/detail.aspx	Todosound	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 15:13:43.824775+03	2026-10-21 16:47:46.065366+03
18	1	1910198330	Наушники меховые зимние утепленные	https://www.wildberries.ru/catalog/1910198330/detail.aspx	\N	\N	\N	\N	\N	\N	\N	2026-10-21 15:13:51.639846+03	2026-10-21 16:47:57.760538+03
20	1	221092413	Беспроводные наушники большие	https://www.wildberries.ru/catalog/221092413/detail.aspx	Maxper	\N	bluetooth	over_ear	t	\N	\N	2026-10-21 15:14:07.93931+03	2026-10-21 16:48:34.168183+03
23	1	366644287	Беспроводные наушники FreeBuds SE 2, голубые	https://www.wildberries.ru/catalog/366644287/detail.aspx	Huawei	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 15:14:31.764328+03	2026-10-21 16:49:11.249355+03
25	1	1277432399	Наушники беспроводные клипсы для айфона и андроид	https://www.wildberries.ru/catalog/1277432399/detail.aspx	FKFM	\N	bluetooth	in_ear	t	\N	\N	2026-10-21 15:14:47.316708+03	2026-10-21 16:49:35.275001+03
26	1	357306971	Tune 520 BT Наушники накладные беспроводные Оригинал	https://www.wildberries.ru/catalog/357306971/detail.aspx	JBL	\N	bluetooth	on_ear	\N	\N	\N	2026-10-21 15:14:55.908806+03	2026-10-21 16:49:47.171427+03
28	1	317560929	Наушники беспроводные маленькие для телефона	https://www.wildberries.ru/catalog/317560929/detail.aspx	FaizFull	\N	bluetooth	in_ear	\N	\N	5.0	2026-10-21 15:15:12.326248+03	2026-10-21 16:50:11.101021+03
30	1	995441255	Наушники беспроводные с ANC ,микрофоном для андроид и iphone	https://www.wildberries.ru/catalog/995441255/detail.aspx	ZIMI	\N	bluetooth	in_ear	t	t	8.0	2026-10-21 15:15:28.893525+03	2026-10-21 16:50:35.362856+03
52	1	142907446	Наушники проводные для телефона андроид с микрофоном	https://www.wildberries.ru/catalog/142907446/detail.aspx	BYZ	\N	wired	in_ear	\N	t	\N	2026-10-21 16:31:32.163837+03	2026-10-21 16:31:32.163837+03
59	1	172295743	Наушники проводные вакуумные 3.5мм для телефона	https://www.wildberries.ru/catalog/172295743/detail.aspx	HOCO	\N	wired	in_ear	\N	t	\N	2026-10-21 16:32:57.541788+03	2026-10-21 16:32:57.541788+03
46	1	835631140	Наушники беспроводные для android и iphone	https://www.wildberries.ru/catalog/835631140/detail.aspx	TechnoPRO	\N	bluetooth	in_ear	\N	\N	12.0	2026-10-21 16:30:16.882472+03	2026-10-21 16:46:45.941403+03
48	1	517647918	Наушники беспроводные большие детские трансформеры и колонка	https://www.wildberries.ru/catalog/517647918/detail.aspx	\N	\N	bluetooth	over_ear	\N	t	18.0	2026-10-21 16:30:41.580203+03	2026-10-21 16:47:10.512852+03
49	1	678290481	Bluetooth-наушники с бесплатным магнитным динамиком	https://www.wildberries.ru/catalog/678290481/detail.aspx	W&O	\N	bluetooth	\N	\N	\N	\N	2026-10-21 16:30:53.330749+03	2026-10-21 16:47:22.225838+03
54	1	1216403002	Беспроводные наушники TWS Realme Buds Air 8 Pro Global	https://www.wildberries.ru/catalog/1216403002/detail.aspx	Realme	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 16:31:56.130049+03	2026-10-21 16:48:22.228466+03
22	1	924376639	Наушники беспроводные с микрофоном для андроид и iphone	https://www.wildberries.ru/catalog/924376639/detail.aspx	Todosound	\N	bluetooth	in_ear	\N	t	150.0	2026-10-21 15:14:23.951151+03	2026-10-21 16:48:59.001501+03
60	1	132670022	Беспроводные наушники XT80 спортивные для андроид	https://www.wildberries.ru/catalog/132670022/detail.aspx	Lenovo	\N	bluetooth	in_ear	\N	\N	48.0	2026-10-21 16:33:09.56032+03	2026-10-21 16:49:23.367505+03
93	1	584589922	Гарнитура игровая Kraken Kitty V3 Pro (RZ04-05170300-R3M1)	https://www.wildberries.ru/catalog/584589922/detail.aspx	Razer	\N	radio	over_ear	\N	\N	\N	2026-10-21 16:50:23.432091+03	2026-10-21 16:50:23.432091+03
96	2	1554929949	Наушники беспроводные AirPro 2 с шумоподавлением для телефона	https://www.ozon.ru/product/naushniki-besprovodnye-airpro-2-s-shumopodavleniem-dlya-telefona-1554929949/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:17.500509+03	2026-10-21 18:14:17.500509+03
97	2	4543309527	Xiaomi REDMI Buds 8 Беспроводные внутриканальные наушники, черные	https://www.ozon.ru/product/xiaomi-redmi-buds-8-besprovodnye-vnutrikanalnye-naushniki-chernye-4543309527/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:17.502021+03	2026-10-21 18:14:17.502021+03
98	2	2842138543	hoco Наушники беспроводные с микрофоном EQ2, черный	https://www.ozon.ru/product/hoco-naushniki-besprovodnye-s-mikrofonom-eq2-chernyy-2842138543/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:17.502914+03	2026-10-21 18:14:17.502914+03
99	2	1831519686	Наушники беспроводные для телефона Air 2 с микрофоном	https://www.ozon.ru/product/naushniki-besprovodnye-dlya-telefona-air-2-s-mikrofonom-1831519686/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:17.503744+03	2026-10-21 18:14:17.503744+03
100	2	4356446371	Наушники Яндекс Дропс с Алисой AI, беспроводные TWS, ANC, IP54, белые	https://www.ozon.ru/product/naushniki-yandeks-drops-s-alisoy-ai-besprovodnye-tws-anc-ip54-belye-4356446371/	\N	\N	bluetooth	in_ear	t	\N	\N	2026-10-21 18:14:17.504607+03	2026-10-21 18:14:17.504607+03
101	2	1716053944	Наушники беспроводные Air 3 вкладыши с микрофоном	https://www.ozon.ru/product/naushniki-besprovodnye-air-3-vkladyshi-s-mikrofonom-1716053944/	\N	\N	bluetooth	in_ear	\N	t	\N	2026-10-21 18:14:17.505706+03	2026-10-21 18:14:17.505706+03
102	2	4356443905	Наушники Яндекс Дропс с Алисой AI, беспроводные TWS, ANC, IP54, черные	https://www.ozon.ru/product/naushniki-yandeks-drops-s-alisoy-ai-besprovodnye-tws-anc-ip54-chernye-4356443905/	\N	\N	bluetooth	in_ear	t	\N	\N	2026-10-21 18:14:17.506962+03	2026-10-21 18:14:17.506962+03
103	2	1850393460	Наушники беспроводные Air 4 вкладыши с шумоподавлением	https://www.ozon.ru/product/naushniki-besprovodnye-air-4-vkladyshi-s-shumopodavleniem-1850393460/	\N	\N	bluetooth	in_ear	t	\N	\N	2026-10-21 18:14:17.507609+03	2026-10-21 18:14:17.507609+03
104	2	1571777762	hoco Наушники беспроводные с микрофоном Hoco W35 MAX, Bluetooth, 3.5 мм, USB Type-C, черный	https://www.ozon.ru/product/hoco-naushniki-besprovodnye-s-mikrofonom-hoco-w35-max-bluetooth-3-5-mm-usb-type-c-chernyy-1571777762/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:17.508187+03	2026-10-21 18:14:17.508187+03
105	2	3372479252	Xiaomi Redmi Buds 8 Lite Наушники беспроводные, белые	https://www.ozon.ru/product/xiaomi-redmi-buds-8-lite-naushniki-besprovodnye-belye-3372479252/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:17.508949+03	2026-10-21 18:14:17.508949+03
106	2	4129261607	Xiaomi REDMI Headphones Neo Беспроводные наушники, sand white	https://www.ozon.ru/product/xiaomi-redmi-headphones-neo-besprovodnye-naushniki-sand-white-4129261607/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:17.509642+03	2026-10-21 18:14:17.509642+03
107	2	3539598554	TWS-наушники Samsung Galaxy Buds 4 Pro Ростест (EAC), черный	https://www.ozon.ru/product/tws-naushniki-samsung-galaxy-buds-4-pro-rostest-eac-chernyy-3539598554/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:17.510321+03	2026-10-21 18:14:17.510321+03
108	2	1682717140	Xiaomi Redmi Buds 6 Play Наушники беспроводные, черные	https://www.ozon.ru/product/xiaomi-redmi-buds-6-play-naushniki-besprovodnye-chernye-1682717140/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:17.511259+03	2026-10-21 18:14:17.511259+03
109	2	3541323478	Наушники беспроводные для телефона, наушники клипсы , с Bluetooth 5.4, для учебы/спорта/работы бежевые с кейсом	https://www.ozon.ru/product/naushniki-besprovodnye-dlya-telefona-naushniki-klipsy-s-bluetooth-5-4-dlya-ucheby-sporta-3541323478/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:17.512297+03	2026-10-21 18:14:17.512297+03
110	2	2844523119	Apple Наушники беспроводные с микрофоном Apple AirPods Pro 3, Bluetooth, USB Type-C, белый	https://www.ozon.ru/product/apple-naushniki-besprovodnye-s-mikrofonom-apple-airpods-pro-3-bluetooth-usb-type-c-belyy-2844523119/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:17.513714+03	2026-10-21 18:14:17.513714+03
111	2	3243316029	JBL Tune 730BT Беспроводные наушники, синие	https://www.ozon.ru/product/jbl-tune-730bt-besprovodnye-naushniki-sinie-3243316029/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:17.514574+03	2026-10-21 18:14:17.514574+03
112	2	4543312295	Xiaomi REDMI Buds 8 Беспроводные внутриканальные наушники, белые	https://www.ozon.ru/product/xiaomi-redmi-buds-8-besprovodnye-vnutrikanalnye-naushniki-belye-4543312295/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:17.515383+03	2026-10-21 18:14:17.515383+03
113	2	2087057420	Наушники беспроводные Hoco с микрофоном	https://www.ozon.ru/product/naushniki-besprovodnye-hoco-s-mikrofonom-2087057420/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:17.516158+03	2026-10-21 18:14:17.516158+03
114	2	5703244913	Наушники беспроводные с микрофоном, Bluetooth, Type-C	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-bluetooth-type-c-5703244913/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.368323+03	2026-10-21 18:14:32.368323+03
115	2	1891251877	Наушники беспроводные AiPods Pro 3 с шумоподавлением для телефона	https://www.ozon.ru/product/naushniki-besprovodnye-aipods-pro-3-s-shumopodavleniem-dlya-telefona-1891251877/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.373359+03	2026-10-21 18:14:32.373359+03
116	2	3872542781	Наушники беспроводные Pro 2	https://www.ozon.ru/product/naushniki-besprovodnye-pro-2-3872542781/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.374375+03	2026-10-21 18:14:32.374375+03
117	2	1869382083	JBL WAVE BEAM 2 Наушники беспроводные, черные	https://www.ozon.ru/product/jbl-wave-beam-2-naushniki-besprovodnye-chernye-1869382083/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.37516+03	2026-10-21 18:14:32.37516+03
95	2	1891267795	Наушники беспроводные AiPods 4 с шумоподавлением для телефона	https://www.ozon.ru/product/naushniki-besprovodnye-aipods-4-s-shumopodavleniem-dlya-telefona-1891267795/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:17.48937+03	2026-10-21 18:14:32.375838+03
119	2	3627230434	Xiaomi REDMI Buds 8 Active Беспроводные вкладыши наушники, черные	https://www.ozon.ru/product/xiaomi-redmi-buds-8-active-besprovodnye-vkladyshi-naushniki-chernye-3627230434/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:32.376486+03	2026-10-21 18:14:32.376486+03
120	2	3030630669	Наушники беспроводные A9 ANC с микрофоном шумоподавлением / Блютуз наушники / Спортивные наушники / Type C	https://www.ozon.ru/product/naushniki-besprovodnye-a9-anc-s-mikrofonom-shumopodavleniem-blyutuz-naushniki-sportivnye-naushniki-3030630669/	\N	\N	bluetooth	\N	t	t	\N	2026-10-21 18:14:32.377239+03	2026-10-21 18:14:32.377239+03
121	2	201501407	Наушники проводные 3.5 jack / GQbox / Вкладыши с микрофоном с разъёмом Jack 3,5 / Белые	https://www.ozon.ru/product/naushniki-provodnye-3-5-jack-gqbox-vkladyshi-s-mikrofonom-s-razemom-jack-3-5-belye-201501407/	\N	\N	wired	in_ear	\N	t	\N	2026-10-21 18:14:32.377985+03	2026-10-21 18:14:32.377985+03
122	2	3545573576	Marshall Наушники с микрофоном Marshall Major V, Bluetooth, 3.5 мм, USB Type-C, черный	https://www.ozon.ru/product/marshall-naushniki-s-mikrofonom-marshall-major-v-bluetooth-3-5-mm-usb-type-c-chernyy-3545573576/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.378577+03	2026-10-21 18:14:32.378577+03
123	2	1769233093	Tecno Buds 4 Air Наушники беспроводные, черные	https://www.ozon.ru/product/tecno-buds-4-air-naushniki-besprovodnye-chernye-1769233093/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.379149+03	2026-10-21 18:14:32.379149+03
124	2	3051797093	IO by Red Square Graphite 2 Pro Wireless USB Type-C Игровые беспроводные наушники, с микрофоном, io341, white	https://www.ozon.ru/product/io-by-red-square-graphite-2-pro-wireless-usb-type-c-igrovye-besprovodnye-naushniki-s-mikrofonom-3051797093/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.379716+03	2026-10-21 18:14:32.379716+03
125	2	3418470312	Наушники AiPods Pro 3 с шумоподавлением. Наушники беспроводные для iOS и Android	https://www.ozon.ru/product/naushniki-aipods-pro-3-s-shumopodavleniem-naushniki-besprovodnye-dlya-ios-i-android-3418470312/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.380279+03	2026-10-21 18:14:32.380279+03
126	2	2265746792	Беспроводные спортивные наушники OWS с заушниками, блютуз гарнитура с микрофоном для бега и смартфона, Bluetooth 5.3 Type-C	https://www.ozon.ru/product/besprovodnye-sportivnye-naushniki-ows-s-zaushnikami-blyutuz-garnitura-s-mikrofonom-dlya-bega-i-2265746792/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.380867+03	2026-10-21 18:14:32.380867+03
127	2	5894630848	Наушники беспроводные Air Pro 3 для айфон с шумоподавлением	https://www.ozon.ru/product/naushniki-besprovodnye-air-pro-3-dlya-ayfon-s-shumopodavleniem-5894630848/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.381438+03	2026-10-21 18:14:32.381438+03
128	2	5413455528	Наушники беспроводные с микрофоном, Bluetooth, USB Type-C, белый, зеркальный	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-bluetooth-usb-type-c-belyy-zerkalnyy-5413455528/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.3821+03	2026-10-21 18:14:32.3821+03
129	2	1883410624	Наушники беспроводные с микрофоном/ наушники накладные	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-naushniki-nakladnye-1883410624/	\N	\N	bluetooth	on_ear	\N	t	\N	2026-10-21 18:14:32.382833+03	2026-10-21 18:14:32.382833+03
130	2	1706475120	Apple Наушники беспроводные с микрофоном Apple AirPods 4 ANC, Bluetooth, USB Type-C, белый, черно-серый	https://www.ozon.ru/product/apple-naushniki-besprovodnye-s-mikrofonom-apple-airpods-4-anc-bluetooth-usb-type-c-belyy-1706475120/	\N	\N	bluetooth	\N	t	t	\N	2026-10-21 18:14:32.383567+03	2026-10-21 18:14:32.383567+03
131	2	1394715680	Axelvox HD242 Полуоткрытые профессиональные динамические наушники	https://www.ozon.ru/product/axelvox-hd242-poluotkrytye-professionalnye-dinamicheskie-naushniki-1394715680/	\N	\N	\N	\N	\N	\N	\N	2026-10-21 18:14:32.384228+03	2026-10-21 18:14:32.384228+03
132	2	5843404546	Наушники беспроводные для телефона EW119 с микрофоном и ENC, Hi-Fi звук, до 65 часов, Bluetooth 6.0, для Android и iPhone	https://www.ozon.ru/product/naushniki-besprovodnye-dlya-telefona-ew119-s-mikrofonom-i-enc-hi-fi-zvuk-do-65-chasov-bluetooth-6-0-5843404546/	\N	\N	bluetooth	\N	\N	t	65.0	2026-10-21 18:14:32.384879+03	2026-10-21 18:14:32.384879+03
133	2	4837032537	Беспроводные наушники PRO 2 с микрофоном Bluetooth ! Для любых устройств! С пассивным шумоподавлением, качественный звук	https://www.ozon.ru/product/besprovodnye-naushniki-pro-2-s-mikrofonom-bluetooth-dlya-lyubyh-ustroystv-s-4837032537/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.385456+03	2026-10-21 18:14:32.385456+03
134	2	5838149159	Наушники беспроводные игровые J0-8. для телефона L it е блютуз c шумоподавлением	https://www.ozon.ru/product/naushniki-besprovodnye-igrovye-j0-8-dlya-telefona-l-it-e-blyutuz-c-shumopodavleniem-5838149159/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.386011+03	2026-10-21 18:14:32.386011+03
135	2	1764079562	Redmi Buds 6 Play Беспроводные наушники, синие	https://www.ozon.ru/product/redmi-buds-6-play-besprovodnye-naushniki-sinie-1764079562/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.386559+03	2026-10-21 18:14:32.386559+03
136	2	5843084660	Наушники беспроводные с микрофоном, Bluetooth, USB Type-C, серебристый	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-bluetooth-usb-type-c-serebristyy-5843084660/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.387141+03	2026-10-21 18:14:32.387141+03
137	2	1692996500	Наушники беспроводные с шумоподавлением AIPODS PPO 2. Беспроводные наушники для телефона. LUX	https://www.ozon.ru/product/naushniki-besprovodnye-s-shumopodavleniem-aipods-ppo-2-besprovodnye-naushniki-dlya-telefona-lux-1692996500/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.387721+03	2026-10-21 18:14:32.387721+03
138	2	4800869820	Наушники беспроводные с микрофоном, Bluetooth, Type-C	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-bluetooth-type-c-4800869820/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.388275+03	2026-10-21 18:14:32.388275+03
139	2	1913261401	Наушники JBL Tune Buds, синий	https://www.ozon.ru/product/naushniki-jbl-tune-buds-siniy-1913261401/	\N	\N	\N	\N	\N	\N	\N	2026-10-21 18:14:32.388889+03	2026-10-21 18:14:32.388889+03
140	2	3539569074	realme Buds T500 Pro Беспроводные вкладыши наушники, желтые	https://www.ozon.ru/product/realme-buds-t500-pro-besprovodnye-vkladyshi-naushniki-zheltye-3539569074/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:32.389437+03	2026-10-21 18:14:32.389437+03
141	2	2195231917	Наушники Sony WI-C100, черный	https://www.ozon.ru/product/naushniki-sony-wi-c100-chernyy-2195231917/	\N	\N	\N	\N	\N	\N	\N	2026-10-21 18:14:32.39+03	2026-10-21 18:14:32.39+03
142	2	5900117167	Наушники беспроводные Air 2	https://www.ozon.ru/product/naushniki-besprovodnye-air-2-5900117167/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.39149+03	2026-10-21 18:14:32.39149+03
143	2	5110990658	Беспроводные наушники Anker Soundcore R50i NC Black, с шумоподавлением	https://www.ozon.ru/product/besprovodnye-naushniki-anker-soundcore-r50i-nc-black-s-shumopodavleniem-5110990658/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.39215+03	2026-10-21 18:14:32.39215+03
144	2	3507271132	Xiaomi REDMI Buds 8 Pro Беспроводные внутриканальные наушники, ледниково-голубые	https://www.ozon.ru/product/xiaomi-redmi-buds-8-pro-besprovodnye-vnutrikanalnye-naushniki-lednikovo-golubye-3507271132/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:32.392831+03	2026-10-21 18:14:32.392831+03
145	2	2153333534	Наушники проводные Fifine H16 Gaming Headsets (Чёрный) большие накладные игровые для пк	https://www.ozon.ru/product/naushniki-provodnye-fifine-h16-gaming-headsets-chernyy-bolshie-nakladnye-igrovye-dlya-pk-2153333534/	\N	\N	wired	on_ear	\N	\N	\N	2026-10-21 18:14:32.393419+03	2026-10-21 18:14:32.393419+03
146	2	1609973238	hoco Наушники беспроводные с микрофоном HOCO W35 Air Triumph, Bluetooth, 3.5 мм, USB Type-C, черный	https://www.ozon.ru/product/hoco-naushniki-besprovodnye-s-mikrofonom-hoco-w35-air-triumph-bluetooth-3-5-mm-usb-type-c-chernyy-1609973238/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.394+03	2026-10-21 18:14:32.394+03
147	2	4670184259	IO by Red Square Graphite 2 Wireless Беспроводные полноразмерные наушники, черные	https://www.ozon.ru/product/io-by-red-square-graphite-2-wireless-besprovodnye-polnorazmernye-naushniki-chernye-4670184259/	\N	\N	bluetooth	over_ear	\N	\N	\N	2026-10-21 18:14:32.394555+03	2026-10-21 18:14:32.394555+03
148	2	3539598633	TWS-наушники Samsung Galaxy Buds 4 Ростест (EAC), белый	https://www.ozon.ru/product/tws-naushniki-samsung-galaxy-buds-4-rostest-eac-belyy-3539598633/	\N	\N	bluetooth	in_ear	\N	\N	\N	2026-10-21 18:14:32.395099+03	2026-10-21 18:14:32.395099+03
149	2	5383126433	Наушники Ai4 для iOS и Android с шумоподавлением. Наушники беспроводные	https://www.ozon.ru/product/naushniki-ai4-dlya-ios-i-android-s-shumopodavleniem-naushniki-besprovodnye-5383126433/	\N	\N	bluetooth	\N	t	\N	\N	2026-10-21 18:14:32.395684+03	2026-10-21 18:14:32.395684+03
150	2	1401457139	Наушники проводные для iPhone/ Наушники Lightning для айфона / GQbox / Белый	https://www.ozon.ru/product/naushniki-provodnye-dlya-iphone-naushniki-lightning-dlya-ayfona-gqbox-belyy-1401457139/	\N	\N	wired	\N	\N	\N	\N	2026-10-21 18:14:32.396303+03	2026-10-21 18:14:32.396303+03
151	2	5919482970	Наушники беспроводные Son y WF-1000, для телефона	https://www.ozon.ru/product/naushniki-besprovodnye-son-y-wf-1000-dlya-telefona-5919482970/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.39688+03	2026-10-21 18:14:32.39688+03
152	2	5889261202	RegalTone Наушники беспроводные с микрофоном Air Pro 3 с шумоподавлением Lux, Bluetooth, USB Type-C, белый, белый матовый	https://www.ozon.ru/product/regaltone-naushniki-besprovodnye-s-mikrofonom-air-pro-3-s-shumopodavleniem-lux-bluetooth-usb-type-5889261202/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.397477+03	2026-10-21 18:14:32.397477+03
153	2	1335623878	наушники беспроводные спортивные на шею с микрофоном с флешкой для телефона	https://www.ozon.ru/product/naushniki-besprovodnye-sportivnye-na-sheyu-s-mikrofonom-s-fleshkoy-dlya-telefona-1335623878/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.398135+03	2026-10-21 18:14:32.398135+03
154	2	1764079713	Redmi Buds 6 Play Беспроводные наушники, розовые	https://www.ozon.ru/product/redmi-buds-6-play-besprovodnye-naushniki-rozovye-1764079713/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.398686+03	2026-10-21 18:14:32.398686+03
155	2	1998118705	hoco Наушники беспроводные с микрофоном Hoco EQ2 Plus, Bluetooth, USB Type-C, черный	https://www.ozon.ru/product/hoco-naushniki-besprovodnye-s-mikrofonom-hoco-eq2-plus-bluetooth-usb-type-c-chernyy-1998118705/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.399232+03	2026-10-21 18:14:32.399232+03
156	2	4031945429	Наушники беспроводные большие Hoco W35	https://www.ozon.ru/product/naushniki-besprovodnye-bolshie-hoco-w35-4031945429/	\N	\N	bluetooth	over_ear	\N	\N	\N	2026-10-21 18:14:32.399774+03	2026-10-21 18:14:32.399774+03
157	2	2451144233	Наушники проводные для телефона, HAPPYAUDIO	https://www.ozon.ru/product/naushniki-provodnye-dlya-telefona-happyaudio-2451144233/	\N	\N	wired	\N	\N	\N	\N	2026-10-21 18:14:32.400332+03	2026-10-21 18:14:32.400332+03
158	2	5679545809	Наушники беспроводные с микрофоном, Bluetooth, USB Type-C, черный	https://www.ozon.ru/product/naushniki-besprovodnye-s-mikrofonom-bluetooth-usb-type-c-chernyy-5679545809/	\N	\N	bluetooth	\N	\N	t	\N	2026-10-21 18:14:32.400871+03	2026-10-21 18:14:32.400871+03
159	2	2559300671	HABBARMERS Наушники проводные с микрофоном, USB Type-C, белый, коричневый	https://www.ozon.ru/product/habbarmers-naushniki-provodnye-s-mikrofonom-usb-type-c-belyy-korichnevyy-2559300671/	\N	\N	wired	\N	\N	t	\N	2026-10-21 18:14:32.40343+03	2026-10-21 18:14:32.40343+03
160	2	1304176255	Наушники проводные Type C / Наушники вакуумные для телефона с микрофоном / для iPhone 15-17 и Android / GQbox / Белый	https://www.ozon.ru/product/naushniki-provodnye-type-c-naushniki-vakuumnye-dlya-telefona-s-mikrofonom-dlya-iphone-15-17-1304176255/	\N	\N	wired	in_ear	\N	t	\N	2026-10-21 18:14:32.404093+03	2026-10-21 18:14:32.404093+03
161	2	3539569158	realme Buds T500 Pro Беспроводные наушники, черные	https://www.ozon.ru/product/realme-buds-t500-pro-besprovodnye-naushniki-chernye-3539569158/	\N	\N	bluetooth	\N	\N	\N	\N	2026-10-21 18:14:32.404655+03	2026-10-21 18:14:32.404655+03
\.


--
-- TOC entry 4976 (class 0 OID 0)
-- Dependencies: 219
-- Name: marketplaces_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.marketplaces_id_seq', 5, true);


--
-- TOC entry 4977 (class 0 OID 0)
-- Dependencies: 223
-- Name: parse_runs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.parse_runs_id_seq', 9, true);


--
-- TOC entry 4978 (class 0 OID 0)
-- Dependencies: 225
-- Name: price_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.price_history_id_seq', 162, true);


--
-- TOC entry 4979 (class 0 OID 0)
-- Dependencies: 221
-- Name: products_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.products_id_seq', 161, true);


--
-- TOC entry 4792 (class 2606 OID 24923)
-- Name: marketplaces marketplaces_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marketplaces
    ADD CONSTRAINT marketplaces_code_key UNIQUE (code);


--
-- TOC entry 4794 (class 2606 OID 24921)
-- Name: marketplaces marketplaces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marketplaces
    ADD CONSTRAINT marketplaces_pkey PRIMARY KEY (id);


--
-- TOC entry 4802 (class 2606 OID 24964)
-- Name: parse_runs parse_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parse_runs
    ADD CONSTRAINT parse_runs_pkey PRIMARY KEY (id);


--
-- TOC entry 4807 (class 2606 OID 24995)
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (id);


--
-- TOC entry 4809 (class 2606 OID 24997)
-- Name: price_history price_history_run_id_product_id_region_currency_price_kind_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_run_id_product_id_region_currency_price_kind_key UNIQUE (run_id, product_id, region, currency, price_kind);


--
-- TOC entry 4798 (class 2606 OID 24943)
-- Name: products products_marketplace_id_external_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_marketplace_id_external_id_key UNIQUE (marketplace_id, external_id);


--
-- TOC entry 4800 (class 2606 OID 24941)
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- TOC entry 4803 (class 1259 OID 25009)
-- Name: idx_price_history_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_price_history_lookup ON public.price_history USING btree (product_id, region, currency, price_kind, observed_at DESC);


--
-- TOC entry 4804 (class 1259 OID 25010)
-- Name: idx_price_history_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_price_history_run ON public.price_history USING btree (run_id);


--
-- TOC entry 4795 (class 1259 OID 25008)
-- Name: idx_products_connection_form; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_products_connection_form ON public.products USING btree (connection_type, form_factor);


--
-- TOC entry 4805 (class 1259 OID 25012)
-- Name: price_history_lookup_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX price_history_lookup_idx ON public.price_history USING btree (product_id, region, currency, price_kind, observed_at DESC);


--
-- TOC entry 4810 (class 1259 OID 25013)
-- Name: price_history_run_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX price_history_run_idx ON public.price_history USING btree (run_id);


--
-- TOC entry 4796 (class 1259 OID 25011)
-- Name: products_connection_form_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX products_connection_form_idx ON public.products USING btree (connection_type, form_factor);


--
-- TOC entry 4812 (class 2606 OID 24965)
-- Name: parse_runs parse_runs_marketplace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parse_runs
    ADD CONSTRAINT parse_runs_marketplace_id_fkey FOREIGN KEY (marketplace_id) REFERENCES public.marketplaces(id);


--
-- TOC entry 4813 (class 2606 OID 24998)
-- Name: price_history price_history_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- TOC entry 4814 (class 2606 OID 25003)
-- Name: price_history price_history_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.parse_runs(id);


--
-- TOC entry 4811 (class 2606 OID 24944)
-- Name: products products_marketplace_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_marketplace_id_fkey FOREIGN KEY (marketplace_id) REFERENCES public.marketplaces(id);


-- Completed on 2026-10-22 21:38:39

--
-- PostgreSQL database dump complete
--

\unrestrict iipnq9MqOqEV01qNzRblbqpfGZq2aOm7WOyc5vbyRl6a5wwga3BeQuKmzfofi2s

