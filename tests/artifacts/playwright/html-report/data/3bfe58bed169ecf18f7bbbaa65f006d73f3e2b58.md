# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: paper-trading-read-architecture.spec.ts >> Paper Trading Read Architecture >> lifecycle state and paused labels render from API response
- Location: e2e\paper-trading-read-architecture.spec.ts:136:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e5]:
    - button "Scanner" [ref=e6] [cursor=pointer]
    - button "Home" [ref=e7] [cursor=pointer]
    - button "Paper Trading" [active] [ref=e8] [cursor=pointer]
  - main [ref=e11]:
    - generic [ref=e12]:
      - generic [ref=e13]:
        - paragraph [ref=e14]: Paper Trading
        - heading "Cash-only execution simulator" [level=1] [ref=e15]
        - paragraph [ref=e16]: TradingView-style practice flow for Nifty 500 cash stocks, connected to your analysis and trade-plan outputs.
      - generic [ref=e17]:
        - generic "INFY-EQ" [ref=e18]: "Engine: STOPPED | Feed: disconnected | Symbols: 1"
        - button "Start Market Engine" [ref=e19] [cursor=pointer]
        - button "Stop Engine" [ref=e20] [cursor=pointer]
        - generic [ref=e21]:
          - generic [ref=e22]: Reset balance
          - spinbutton "Reset balance" [ref=e23]: "1000000"
        - button "Refresh" [ref=e24] [cursor=pointer]
        - button "Live price on" [ref=e25] [cursor=pointer]
        - button "Reset account" [ref=e26] [cursor=pointer]
    - generic [ref=e27]:
      - article [ref=e28]:
        - generic [ref=e29]:
          - text: Balance
          - button "More information" [ref=e31]: ℹ️
        - strong [ref=e32]: ₹10,00,000.00
        - paragraph [ref=e33]: Paper account metric.
      - article [ref=e34]:
        - generic [ref=e35]:
          - text: Equity
          - button "More information" [ref=e37]: ℹ️
        - strong [ref=e38]: ₹10,00,000.00
        - paragraph [ref=e39]: Paper account metric.
      - article [ref=e40]:
        - generic [ref=e41]:
          - text: Realized P&L
          - button "More information" [ref=e43]: ℹ️
        - strong [ref=e44]: ₹0.00
        - paragraph [ref=e45]: Paper account metric.
      - article [ref=e46]:
        - generic [ref=e47]:
          - text: Unrealized P&L
          - button "More information" [ref=e49]: ℹ️
        - strong [ref=e50]: ₹0.00
        - paragraph [ref=e51]: Paper account metric.
      - article [ref=e52]:
        - generic [ref=e53]:
          - text: Invested
          - button "More information" [ref=e55]: ℹ️
        - strong [ref=e56]: ₹0.00
        - paragraph [ref=e57]: Paper account metric.
      - article [ref=e58]:
        - generic [ref=e59]:
          - text: Available cash
          - button "More information" [ref=e61]: ℹ️
        - strong [ref=e62]: ₹10,00,000.00
        - paragraph [ref=e63]: Balance after reserving pending buy orders.
      - article [ref=e64]:
        - generic [ref=e65]:
          - text: Open positions
          - button "More information" [ref=e67]: ℹ️
        - strong [ref=e68]: "0"
        - paragraph [ref=e69]: Paper account metric.
      - article [ref=e70]:
        - text: Open orders
        - strong [ref=e71]: "0"
        - paragraph [ref=e72]: Paper account metric.
    - generic [ref=e74]:
      - generic [ref=e75]:
        - generic [ref=e76]:
          - text: Total capital
          - strong [ref=e77]: ₹10,00,000.00
          - paragraph [ref=e78]: Virtual account value
        - generic [ref=e79]:
          - generic [ref=e80]:
            - text: Available funds
            - button "More information" [ref=e82]: ℹ️
          - strong [ref=e83]: ₹10,00,000.00
          - paragraph [ref=e84]: Cash available to place buys
        - generic [ref=e85]:
          - text: Invested value
          - strong [ref=e86]: ₹0.00
          - paragraph [ref=e87]: Sum of open positions
        - generic [ref=e88]:
          - generic [ref=e89]:
            - text: Total P&L
            - button "More information" [ref=e91]: ℹ️
          - strong [ref=e92]: ₹0.00
          - paragraph [ref=e93]: Unrealized + realized
        - generic [ref=e94]:
          - generic [ref=e95]:
            - text: Daily P&L
            - button "More information" [ref=e97]: ℹ️
          - strong [ref=e98]: ₹0.00
          - paragraph [ref=e99]: 0.00%
        - generic [ref=e100]:
          - generic [ref=e101]:
            - text: Market status
            - button "More information" [ref=e103]: ℹ️
          - strong [ref=e104]: OPEN 🟢
          - paragraph [ref=e105]: Based on IST clock
      - generic [ref=e106]:
        - button "Quick Buy" [ref=e107] [cursor=pointer]
        - button "Quick Sell" [ref=e108] [cursor=pointer]
    - generic [ref=e111]: INFY-EQ limit buy waiting for entry at Rs 0.0.
    - generic [ref=e112]:
      - generic [ref=e114]:
        - tablist "Paper trading data tabs" [ref=e115]:
          - button "Positions" [ref=e116] [cursor=pointer]
          - button "Open Orders" [ref=e117] [cursor=pointer]
          - button "History" [ref=e118] [cursor=pointer]
          - button "Analytics" [ref=e119] [cursor=pointer]
          - button "Alerts" [ref=e120] [cursor=pointer]
          - button "Account" [ref=e121] [cursor=pointer]
        - generic [ref=e122]:
          - button "Square Off ALL" [disabled] [ref=e123] [cursor=pointer]
          - button "More information" [ref=e125]: ℹ️
        - generic [ref=e126]: No open positions
      - generic [ref=e127]:
        - generic [ref=e128]:
          - generic [ref=e129]:
            - generic [ref=e130]:
              - paragraph [ref=e131]: Order ticket
              - heading "Place paper order" [level=2] [ref=e132]
            - generic [ref=e133]: Cash only
          - generic [ref=e134]:
            - generic [ref=e135]:
              - generic [ref=e136]:
                - text: Symbol
                - button "More information" [ref=e138]: ℹ️
              - combobox [ref=e139]:
                - option "360ONE-EQ"
                - option "3MINDIA-EQ"
                - option "ABB-EQ"
                - option "ACC-EQ"
                - option "ACMESOLAR-EQ"
                - option "AIAENG-EQ"
                - option "APLAPOLLO-EQ"
                - option "ASKAUTOLTD-EQ"
                - option "AUBANK-EQ"
                - option "AWL-EQ"
                - option "AXISCADES-EQ"
                - option "AADHARHFC-EQ"
                - option "AARTIDRUGS-EQ"
                - option "AARTIIND-EQ"
                - option "AARTIPHARM-EQ"
                - option "AAVAS-EQ"
                - option "ABBOTINDIA-EQ"
                - option "ACE-EQ"
                - option "ACUTAAS-EQ"
                - option "ADANIENSOL-EQ"
                - option "ADANIENT-EQ"
                - option "ADANIGREEN-EQ"
                - option "ADANIPORTS-EQ"
                - option "ADANIPOWER-EQ"
                - option "ATGL-EQ"
                - option "ABCAPITAL-EQ"
                - option "ABFRL-EQ"
                - option "ABLBL-EQ"
                - option "ABREL-EQ"
                - option "ABSLAMC-EQ"
                - option "CPPLUS-EQ"
                - option "AVL-EQ"
                - option "ADVENZYMES-EQ"
                - option "AEGISLOG-EQ"
                - option "AEGISVOPAK-EQ"
                - option "AEQUS-EQ"
                - option "AETHER-EQ"
                - option "AFCONS-EQ"
                - option "AFFLE-EQ"
                - option "AHLUCONT-EQ"
                - option "AJANTPHARM-EQ"
                - option "AKUMS-EQ"
                - option "APLLTD-EQ"
                - option "ALIVUS-EQ"
                - option "ALKEM-EQ"
                - option "ALKYLAMINE-EQ"
                - option "ABDL-EQ"
                - option "ALOKINDS-EQ"
                - option "ARE&M-EQ"
                - option "AMBER-EQ"
                - option "AMBUJACEM-EQ"
                - option "ANANDRATHI-EQ"
                - option "ANANTRAJ-EQ"
                - option "ANGELONE-EQ"
                - option "ANTHEM-EQ"
                - option "ANURAS-EQ"
                - option "APARINDS-EQ"
                - option "APOLLOHOSP-EQ"
                - option "APOLLO-EQ"
                - option "APOLLOTYRE-EQ"
                - option "APTUS-EQ"
                - option "ACI-EQ"
                - option "ARVINDFASN-EQ"
                - option "ARVIND-EQ"
                - option "ASAHIINDIA-EQ"
                - option "ASHAPURMIN-EQ"
                - option "ASHOKLEY-EQ"
                - option "ASHOKA-EQ"
                - option "ASIANPAINT-EQ"
                - option "ASTERDM-EQ"
                - option "ASTRAMICRO-EQ"
                - option "ASTRAL-EQ"
                - option "ATHERENERG-EQ"
                - option "ATLANTAELE-BE"
                - option "ATUL-EQ"
                - option "AURIONPRO-EQ"
                - option "AUROPHARMA-EQ"
                - option "AIIL-EQ"
                - option "AVALON-EQ"
                - option "AVANTIFEED-EQ"
                - option "DMART-EQ"
                - option "CCAVENUE-EQ"
                - option "AWFIS-EQ"
                - option "AXISBANK-EQ"
                - option "AZAD-EQ"
                - option "BEML-EQ"
                - option "BLS-EQ"
                - option "BSE-EQ"
                - option "BAJAJ-AUTO-EQ"
                - option "BAJAJELEC-EQ"
                - option "BAJFINANCE-EQ"
                - option "BAJAJFINSV-EQ"
                - option "BAJAJHLDNG-EQ"
                - option "BAJAJHFL-EQ"
                - option "BALAMINES-EQ"
                - option "BALKRISIND-EQ"
                - option "BALRAMCHIN-EQ"
                - option "BALUFORGE-EQ"
                - option "BANCOINDIA-EQ"
                - option "BANDHANBNK-EQ"
                - option "BANKBARODA-EQ"
                - option "BANKINDIA-EQ"
                - option "MAHABANK-EQ"
                - option "BATAINDIA-EQ"
                - option "BAYERCROP-EQ"
                - option "BELRISE-EQ"
                - option "BERGEPAINT-EQ"
                - option "BDL-EQ"
                - option "BEL-EQ"
                - option "BHARATFORG-EQ"
                - option "BHEL-EQ"
                - option "BPCL-EQ"
                - option "BHARTIARTL-EQ"
                - option "BHARTIHEXA-EQ"
                - option "BIKAJI-EQ"
                - option "GROWW-EQ"
                - option "BIOCON-EQ"
                - option "BIRLACORPN-EQ"
                - option "BSOFT-EQ"
                - option "BBOX-EQ"
                - option "BLACKBUCK-EQ"
                - option "BLUEDART-EQ"
                - option "BLUEJET-EQ"
                - option "BLUESTARCO-EQ"
                - option "BLUESTONE-EQ"
                - option "BBTC-EQ"
                - option "BORORENEW-EQ"
                - option "BOSCHLTD-EQ"
                - option "FIRSTCRY-EQ"
                - option "BRIGADE-EQ"
                - option "BRITANNIA-EQ"
                - option "MAPMYINDIA-EQ"
                - option "CCL-EQ"
                - option "CESC-EQ"
                - option "CGPOWER-EQ"
                - option "CIEINDIA-EQ"
                - option "CMSINFO-EQ"
                - option "CORONA-EQ"
                - option "CRISIL-EQ"
                - option "CSBBANK-EQ"
                - option "CAMPUS-EQ"
                - option "CANFINHOME-EQ"
                - option "CANBK-EQ"
                - option "CANHLIFE-EQ"
                - option "CRAMC-EQ"
                - option "CAPILLARY-EQ"
                - option "CAPLIPOINT-EQ"
                - option "CGCL-EQ"
                - option "CARBORUNIV-EQ"
                - option "CARTRADE-EQ"
                - option "CASTROLIND-EQ"
                - option "CEATLTD-EQ"
                - option "CELLO-EQ"
                - option "CEMPRO-EQ"
                - option "CENTRALBK-EQ"
                - option "CDSL-EQ"
                - option "CENTURYPLY-EQ"
                - option "CERA-EQ"
                - option "CHALET-EQ"
                - option "CHAMBLFERT-EQ"
                - option "CHENNPETRO-EQ"
                - option "CHOICEIN-EQ"
                - option "CHOLAHLDNG-EQ"
                - option "CHOLAFIN-EQ"
                - option "CIGNITITEC-EQ"
                - option "CIPLA-EQ"
                - option "CUB-EQ"
                - option "CLEAN-EQ"
                - option "COALINDIA-EQ"
                - option "COCHINSHIP-EQ"
                - option "COFORGE-EQ"
                - option "COHANCE-EQ"
                - option "COLPAL-EQ"
                - option "CAMS-EQ"
                - option "CONCORDBIO-EQ"
                - option "CONCOR-EQ"
                - option "COROMANDEL-EQ"
                - option "CRAFTSMAN-EQ"
                - option "CREDITACC-EQ"
                - option "CRIZAC-EQ"
                - option "CROMPTON-EQ"
                - option "CUMMINSIND-EQ"
                - option "CUPID-EQ"
                - option "CYIENT-EQ"
                - option "DCBBANK-EQ"
                - option "DCMSHRIRAM-EQ"
                - option "DLF-EQ"
                - option "DOMS-EQ"
                - option "DABUR-EQ"
                - option "DALBHARAT-EQ"
                - option "DATAPATTNS-EQ"
                - option "DATAMATICS-EQ"
                - option "DEEPAKFERT-EQ"
                - option "DEEPAKNTR-EQ"
                - option "DELHIVERY-EQ"
                - option "DEVYANI-EQ"
                - option "DIACABS-EQ"
                - option "DBL-EQ"
                - option "DIVISLAB-EQ"
                - option "DIXON-EQ"
                - option "AGARWALEYE-EQ"
                - option "LALPATHLAB-EQ"
                - option "DRREDDY-EQ"
                - option "DUMMYALCAR-EQ"
                - option "DUMMYVEDL1-EQ"
                - option "DUMMYVEDL2-EQ"
                - option "DUMMYVEDL3-EQ"
                - option "DUMMYVEDL4-EQ"
                - option "DYNAMATECH-EQ"
                - option "EIDPARRY-EQ"
                - option "EIHOTEL-EQ"
                - option "EPL-EQ"
                - option "EDELWEISS-EQ"
                - option "EICHERMOT-EQ"
                - option "ELECON-EQ"
                - option "EMIL-EQ"
                - option "ELECTCAST-EQ"
                - option "ELGIEQUIP-EQ"
                - option "ELLEN-EQ"
                - option "EMAMILTD-EQ"
                - option "EMBDL-BE"
                - option "EMCURE-EQ"
                - option "EMMVEE-EQ"
                - option "ENDURANCE-EQ"
                - option "ENGINERSIN-EQ"
                - option "ENTERO-EQ"
                - option "EIEL-EQ"
                - option "EQUITASBNK-EQ"
                - option "ERIS-EQ"
                - option "ESCORTS-EQ"
                - option "ETERNAL-EQ"
                - option "ETHOSLTD-EQ"
                - option "EUREKAFORB-EQ"
                - option "EXIDEIND-EQ"
                - option "NYKAA-EQ"
                - option "FEDFINA-EQ"
                - option "FEDERALBNK-EQ"
                - option "FACT-EQ"
                - option "FIEMIND-EQ"
                - option "FINCABLES-EQ"
                - option "FINPIPE-EQ"
                - option "FSL-EQ"
                - option "FIVESTAR-EQ"
                - option "FORCEMOT-EQ"
                - option "FORTIS-EQ"
                - option "UTLSOLAR-EQ"
                - option "GAIL-EQ"
                - option "GVT&D-EQ"
                - option "GHCL-EQ"
                - option "GMMPFAUDLR-EQ"
                - option "GMRAIRPORT-EQ"
                - option "GMRP&UI-EQ"
                - option "GABRIEL-EQ"
                - option "GALLANTT-EQ"
                - option "GRSE-EQ"
                - option "GRWRHITECH-EQ"
                - option "GICRE-EQ"
                - option "GILLETTE-EQ"
                - option "GLAND-EQ"
                - option "GLAXO-EQ"
                - option "GLENMARK-EQ"
                - option "MEDANTA-EQ"
                - option "GODIGIT-EQ"
                - option "GPIL-EQ"
                - option "GODFRYPHLP-EQ"
                - option "GODREJAGRO-EQ"
                - option "GODREJCP-EQ"
                - option "GODREJIND-EQ"
                - option "GODREJPROP-EQ"
                - option "GOKEX-EQ"
                - option "GOKULAGRO-EQ"
                - option "GRANULES-EQ"
                - option "GRAPHITE-EQ"
                - option "GRASIM-EQ"
                - option "GRAVITA-EQ"
                - option "GESHIP-EQ"
                - option "GREAVESCOT-EQ"
                - option "GAEL-EQ"
                - option "FLUOROCHEM-EQ"
                - option "GMDCLTD-EQ"
                - option "GNFC-EQ"
                - option "GPPL-EQ"
                - option "GSFC-EQ"
                - option "GSPL-EQ"
                - option "HEG-EQ"
                - option "HGINFRA-EQ"
                - option "HBLENGINE-EQ"
                - option "HCLTECH-EQ"
                - option "HDBFS-EQ"
                - option "HDFCAMC-EQ"
                - option "HDFCBANK-EQ"
                - option "HDFCLIFE-EQ"
                - option "HFCL-EQ"
                - option "HAPPSTMNDS-EQ"
                - option "HAVELLS-EQ"
                - option "HCG-EQ"
                - option "HEMIPROP-EQ"
                - option "HERITGFOOD-EQ"
                - option "HEROMOTOCO-EQ"
                - option "HEXT-EQ"
                - option "HSCL-EQ"
                - option "HINDALCO-EQ"
                - option "HAL-EQ"
                - option "HCC-EQ"
                - option "HINDCOPPER-EQ"
                - option "HINDPETRO-EQ"
                - option "HINDUNILVR-EQ"
                - option "HINDZINC-EQ"
                - option "POWERINDIA-EQ"
                - option "HOMEFIRST-EQ"
                - option "HONASA-EQ"
                - option "HONAUT-EQ"
                - option "HUDCO-EQ"
                - option "HYUNDAI-EQ"
                - option "ICICIBANK-EQ"
                - option "ICICIGI-EQ"
                - option "ICICIAMC-EQ"
                - option "ICICIPRULI-EQ"
                - option "IDBI-EQ"
                - option "IDFCFIRSTB-EQ"
                - option "IFBIND-EQ"
                - option "IFCI-EQ"
                - option "IIFLCAPS-EQ"
                - option "IIFL-EQ"
                - option "INOXINDIA-EQ"
                - option "IRB-EQ"
                - option "IRCON-EQ"
                - option "ITCHOTELS-EQ"
                - option "ITC-EQ"
                - option "ITI-EQ"
                - option "INDGN-EQ"
                - option "INDIACEM-EQ"
                - option "INDIAGLYCO-EQ"
                - option "INDIASHLTR-EQ"
                - option "INDIAMART-EQ"
                - option "INDIANB-EQ"
                - option "IEX-EQ"
                - option "INDHOTEL-EQ"
                - option "IMFA-EQ"
                - option "IOC-EQ"
                - option "IOB-EQ"
                - option "IRCTC-EQ"
                - option "IRFC-EQ"
                - option "IREDA-EQ"
                - option "INDIGOPNTS-EQ"
                - option "ICIL-EQ"
                - option "IGL-EQ"
                - option "INDUSTOWER-EQ"
                - option "INDUSINDBK-EQ"
                - option "NAUKRI-EQ"
                - option "INFY-EQ" [selected]
                - option "INOXGREEN-EQ"
                - option "INOXWIND-EQ"
                - option "INTELLECT-EQ"
                - option "INDIGO-EQ"
                - option "IGIL-EQ"
                - option "IKS-EQ"
                - option "IONEXCHANG-EQ"
                - option "IPCALAB-EQ"
                - option "JBCHEPHARM-EQ"
                - option "JKCEMENT-EQ"
                - option "JBMA-EQ"
                - option "JKLAKSHMI-EQ"
                - option "JKPAPER-EQ"
                - option "JKTYRE-EQ"
                - option "JMFINANCIL-EQ"
                - option "JSWCEMENT-EQ"
                - option "JSWDULUX-EQ"
                - option "JSWENERGY-EQ"
                - option "JSWINFRA-EQ"
                - option "JSWSTEEL-EQ"
                - option "JAIBALAJI-EQ"
                - option "JAINREC-EQ"
                - option "JPPOWER-EQ"
                - option "J&KBANK-EQ"
                - option "JAMNAAUTO-EQ"
                - option "JSFB-EQ"
                - option "JAYNECOIND-EQ"
                - option "JSLL-EQ"
                - option "JINDALSAW-EQ"
                - option "JSL-EQ"
                - option "JINDALSTEL-EQ"
                - option "JIOFIN-EQ"
                - option "JUBLFOOD-EQ"
                - option "JUBLINGREA-EQ"
                - option "JUBLPHARMA-EQ"
                - option "JLHL-EQ"
                - option "JWL-EQ"
                - option "JUSTDIAL-EQ"
                - option "JYOTHYLAB-EQ"
                - option "JYOTICNC-EQ"
                - option "KPRMILL-EQ"
                - option "KEI-EQ"
                - option "KNRCON-EQ"
                - option "KPIGREEN-EQ"
                - option "KPITTECH-EQ"
                - option "KRBL-EQ"
                - option "KRN-EQ"
                - option "KSB-EQ"
                - option "KAJARIACER-EQ"
                - option "KPIL-EQ"
                - option "KALYANKJIL-EQ"
                - option "KANSAINER-EQ"
                - option "KTKBANK-EQ"
                - option "KARURVYSYA-EQ"
                - option "KSCL-EQ"
                - option "KAYNES-EQ"
                - option "KEC-EQ"
                - option "KFINTECH-EQ"
                - option "KIRLOSBROS-EQ"
                - option "KIRLOSENG-EQ"
                - option "KIRLPNU-EQ"
                - option "KITEX-EQ"
                - option "KOTAKBANK-EQ"
                - option "KIMS-EQ"
                - option "LTF-EQ"
                - option "LTTS-EQ"
                - option "LGEINDIA-EQ"
                - option "LICHSGFIN-EQ"
                - option "LTFOODS-EQ"
                - option "LTM-EQ"
                - option "LT-EQ"
                - option "LATENTVIEW-EQ"
                - option "LAURUSLABS-EQ"
                - option "LXCHEM-EQ"
                - option "IXIGO-EQ"
                - option "THELEELA-EQ"
                - option "LEMONTREE-EQ"
                - option "LENSKART-EQ"
                - option "LICI-EQ"
                - option "LINDEINDIA-EQ"
                - option "LLOYDSENGG-EQ"
                - option "LLOYDSENT-EQ"
                - option "LLOYDSME-EQ"
                - option "LODHA-EQ"
                - option "LUMAXTECH-EQ"
                - option "LUPIN-EQ"
                - option "MMTC-EQ"
                - option "MOIL-EQ"
                - option "MRF-EQ"
                - option "MSTCLTD-EQ"
                - option "MTARTECH-EQ"
                - option "MGL-EQ"
                - option "MAHSCOOTER-EQ"
                - option "MAHSEAMLES-EQ"
                - option "M&MFIN-EQ"
                - option "M&M-EQ"
                - option "MANAPPURAM-EQ"
                - option "MRPL-EQ"
                - option "MANKIND-EQ"
                - option "MANORAMA-EQ"
                - option "MARICO-EQ"
                - option "MARKSANS-EQ"
                - option "MARUTI-EQ"
                - option "MASTEK-EQ"
                - option "MFSL-EQ"
                - option "MAXHEALTH-EQ"
                - option "MAZDOCK-EQ"
                - option "MEDPLUS-EQ"
                - option "MEESHO-EQ"
                - option "METROPOLIS-EQ"
                - option "MINDACORP-EQ"
                - option "MIDHANI-EQ"
                - option "MSUMI-EQ"
                - option "MOTILALOFS-EQ"
                - option "MPHASIS-EQ"
                - option "BECTORFOOD-EQ"
                - option "MCX-EQ"
                - option "MUTHOOTFIN-EQ"
                - option "NATCOPHARM-EQ"
                - option "NBCC-EQ"
                - option "NCC-EQ"
                - option "NEOGEN-EQ"
                - option "NESCO-EQ"
                - option "NHPC-EQ"
                - option "NLCINDIA-EQ"
                - option "NMDC-EQ"
                - option "NSLNISP-EQ"
                - option "NTPCGREEN-EQ"
                - option "NTPC-EQ"
                - option "NH-EQ"
                - option "NATIONALUM-EQ"
                - option "NFL-EQ"
                - option "NAVA-EQ"
                - option "NAVINFLUOR-EQ"
                - option "NAZARA-EQ"
                - option "NESTLEIND-EQ"
                - option "NETWEB-EQ"
                - option "NETWORK18-EQ"
                - option "NEULANDLAB-EQ"
                - option "NEWGEN-EQ"
                - option "NAM-INDIA-EQ"
                - option "NIVABUPA-EQ"
                - option "NUVAMA-EQ"
                - option "NUVOCO-EQ"
                - option "OBEROIRLTY-EQ"
                - option "ONGC-EQ"
                - option "OIL-EQ"
                - option "OLAELEC-EQ"
                - option "OLECTRA-EQ"
                - option "PAYTM-EQ"
                - option "ONESOURCE-EQ"
                - option "OPTIEMUS-EQ"
                - option "OFSS-EQ"
                - option "ORIENTCEM-EQ"
                - option "ORKLAINDIA-EQ"
                - option "OSWALPUMPS-EQ"
                - option "PNGJL-EQ"
                - option "POLICYBZR-EQ"
                - option "PCJEWELLER-EQ"
                - option "PCBL-EQ"
                - option "PGEL-EQ"
                - option "PIIND-EQ"
                - option "PNBHOUSING-EQ"
                - option "PNCINFRA-EQ"
                - option "PTC-EQ"
                - option "PTCIL-EQ"
                - option "PVRINOX-EQ"
                - option "PAGEIND-EQ"
                - option "PARADEEP-EQ"
                - option "PARAS-EQ"
                - option "PARKHOSPS-EQ"
                - option "PATANJALI-EQ"
                - option "PGIL-EQ"
                - option "PERSISTENT-EQ"
                - option "PETRONET-EQ"
                - option "PFIZER-EQ"
                - option "PHOENIXLTD-EQ"
                - option "PWL-EQ"
                - option "PICCADIL-EQ"
                - option "PIDILITIND-EQ"
                - option "PINELABS-EQ"
                - option "PIRAMALFIN-EQ"
                - option "PPLPHARMA-EQ"
                - option "POLYMED-EQ"
                - option "POLYCAB-EQ"
                - option "POONAWALLA-EQ"
                - option "PFC-EQ"
                - option "POWERGRID-EQ"
                - option "POWERMECH-EQ"
                - option "PRAJIND-EQ"
                - option "PREMIERENE-EQ"
                - option "PRESTIGE-EQ"
                - option "PRICOLLTD-EQ"
                - option "PFOCUS-EQ"
                - option "PRSMJOHNSN-EQ"
                - option "PRIVISCL-EQ"
                - option "PRUDENT-EQ"
                - option "PNB-EQ"
                - option "PURVA-EQ"
                - option "QPOWER-EQ"
                - option "QUESS-EQ"
                - option "RRKABEL-EQ"
                - option "RBLBANK-EQ"
                - option "RECLTD-EQ"
                - option "RHIM-EQ"
                - option "RITES-EQ"
                - option "RADICO-EQ"
                - option "RVNL-EQ"
                - option "RAILTEL-EQ"
                - option "RAIN-EQ"
                - option "RAINBOW-EQ"
                - option "RALLIS-EQ"
                - option "RKFORGE-EQ"
                - option "RCF-EQ"
                - option "RATEGAIN-EQ"
                - option "RTNINDIA-EQ"
                - option "RTNPOWER-EQ"
                - option "RAYMONDLSL-EQ"
                - option "REDINGTON-EQ"
                - option "REDTAPE-EQ"
                - option "REFEX-EQ"
                - option "RELAXO-EQ"
                - option "RELIANCE-EQ"
                - option "RPOWER-EQ"
                - option "RELIGARE-EQ"
                - option "RBA-EQ"
                - option "ROUTE-EQ"
                - option "RUBICON-EQ"
                - option "SBFC-EQ"
                - option "SBICARD-EQ"
                - option "SBILIFE-EQ"
                - option "SJVN-EQ"
                - option "SKFINDUS-EQ"
                - option "SKFINDIA-EQ"
                - option "SKYGOLD-EQ"
                - option "SMLMAH-EQ"
                - option "SRF-EQ"
                - option "SAATVIKGL-EQ"
                - option "SAFARI-EQ"
                - option "SAGILITY-EQ"
                - option "SAILIFE-EQ"
                - option "SAMHI-EQ"
                - option "SAMMAANCAP-EQ"
                - option "MOTHERSON-EQ"
                - option "SANDUMA-EQ"
                - option "SANSERA-EQ"
                - option "SAPPHIRE-EQ"
                - option "SARDAEN-EQ"
                - option "SAREGAMA-EQ"
                - option "SCHAEFFLER-EQ"
                - option "SCHNEIDER-BE"
                - option "SENCO-EQ"
                - option "STYL-EQ"
                - option "SHAILY-EQ"
                - option "SHAKTIPUMP-EQ"
                - option "SHARDACROP-EQ"
                - option "SHAREINDIA-EQ"
                - option "SFL-EQ"
                - option "SHILPAMED-EQ"
                - option "SCI-EQ"
                - option "SHREECEM-EQ"
                - option "RENUKA-EQ"
                - option "SHRIRAMFIN-EQ"
                - option "SHRIPISTON-EQ"
                - option "SHYAMMETL-EQ"
                - option "ENRIN-EQ"
                - option "SIEMENS-EQ"
                - option "SIGNATURE-EQ"
                - option "SKIPPER-EQ"
                - option "SMARTWORKS-EQ"
                - option "SOBHA-EQ"
                - option "SOLARINDS-EQ"
                - option "SONACOMS-EQ"
                - option "SONATSOFTW-EQ"
                - option "SOUTHBANK-EQ"
                - option "LOTUSDEV-EQ"
                - option "STARCEMENT-EQ"
                - option "STARHEALTH-EQ"
                - option "SBIN-EQ"
                - option "SAIL-EQ"
                - option "SWSOLAR-EQ"
                - option "STLTECH-EQ"
                - option "STAR-EQ"
                - option "STYRENIX-EQ"
                - option "SUBROS-EQ"
                - option "SUDARSCHEM-EQ"
                - option "SUDEEPPHRM-EQ"
                - option "SUMICHEM-EQ"
                - option "SPARC-EQ"
                - option "SUNPHARMA-EQ"
                - option "SUNTV-EQ"
                - option "SUNDARMFIN-EQ"
                - option "SUNTECK-EQ"
                - option "SUPREMEIND-EQ"
                - option "SPLPETRO-EQ"
                - option "SUPRIYA-EQ"
                - option "SURYAROSNI-EQ"
                - option "SUZLON-EQ"
                - option "SWANCORP-EQ"
                - option "SWIGGY-EQ"
                - option "SYNGENE-EQ"
                - option "SYRMA-EQ"
                - option "TARC-EQ"
                - option "TBOTEK-EQ"
                - option "TDPOWERSYS-EQ"
                - option "TSFINV-EQ"
                - option "TVSMOTOR-EQ"
                - option "TVSSCS-BE"
                - option "TMB-EQ"
                - option "TANLA-EQ"
                - option "TATACAP-EQ"
                - option "TATACHEM-EQ"
                - option "TATACOMM-EQ"
                - option "TCS-EQ"
                - option "TATACONSUM-EQ"
                - option "TATAELXSI-EQ"
                - option "TATAINVEST-EQ"
                - option "TMCV-EQ"
                - option "TMPV-EQ"
                - option "TATAPOWER-EQ"
                - option "TATASTEEL-EQ"
                - option "TATATECH-EQ"
                - option "TTML-EQ"
                - option "TECHM-EQ"
                - option "TECHNOE-EQ"
                - option "TEGA-EQ"
                - option "TEJASNET-EQ"
                - option "TENNIND-EQ"
                - option "TEXRAIL-EQ"
                - option "THANGAMAYL-EQ"
                - option "ANUP-EQ"
                - option "NIACL-EQ"
                - option "RAMCOCEM-EQ"
                - option "THERMAX-EQ"
                - option "THOMASCOOK-EQ"
                - option "THYROCARE-EQ"
                - option "TI-EQ"
                - option "TIMETECHNO-EQ"
                - option "TIMKEN-EQ"
                - option "TIPSMUSIC-EQ"
                - option "TITAGARH-EQ"
                - option "TITAN-EQ"
                - option "TORNTPHARM-EQ"
                - option "TORNTPOWER-EQ"
                - option "TARIL-EQ"
                - option "TRANSRAILL-EQ"
                - option "TRAVELFOOD-EQ"
                - option "TRENT-EQ"
                - option "TRIDENT-EQ"
                - option "TRIVENI-EQ"
                - option "TRITURBINE-EQ"
                - option "TIINDIA-EQ"
                - option "UCOBANK-EQ"
                - option "UNOMINDA-EQ"
                - option "UPL-EQ"
                - option "UTIAMC-EQ"
                - option "UJJIVANSFB-EQ"
                - option "ULTRACEMCO-EQ"
                - option "UNIONBANK-EQ"
                - option "UBL-EQ"
                - option "UNITDSPR-EQ"
                - option "URBANCO-EQ"
                - option "USHAMART-EQ"
                - option "VGUARD-EQ"
                - option "VMART-EQ"
                - option "VIPIND-EQ"
                - option "V2RETAIL-EQ"
                - option "WABAG-EQ"
                - option "VAIBHAVGBL-EQ"
                - option "DBREALTY-EQ"
                - option "VTL-EQ"
                - option "VARROC-EQ"
                - option "VBL-EQ"
                - option "MANYAVAR-EQ"
                - option "VEDL-EQ"
                - option "VIJAYA-EQ"
                - option "VIKRAMSOLR-EQ"
                - option "VMM-EQ"
                - option "VIYASH-EQ"
                - option "IDEA-EQ"
                - option "VOLTAMP-EQ"
                - option "VOLTAS-EQ"
                - option "WAAREEENER-EQ"
                - option "WAAREERTL-EQ"
                - option "WAKEFIT-EQ"
                - option "WEWORK-EQ"
                - option "WEBELSOLAR-EQ"
                - option "WELCORP-EQ"
                - option "WELENT-EQ"
                - option "WELSPUNLIV-EQ"
                - option "WESTLIFE-EQ"
                - option "WHIRLPOOL-EQ"
                - option "WIPRO-EQ"
                - option "WOCKPHARMA-EQ"
                - option "YATHARTH-EQ"
                - option "YESBANK-EQ"
                - option "ZFCVINDIA-EQ"
                - option "ZAGGLE-EQ"
                - option "ZEEL-EQ"
                - option "ZENTEC-EQ"
                - option "ZENSARTECH-EQ"
                - option "ZYDUSLIFE-EQ"
                - option "ZYDUSWELL-EQ"
                - option "ECLERX-EQ"
            - generic [ref=e140]:
              - generic [ref=e141]:
                - text: Side
                - button "More information" [ref=e143]: ℹ️
              - combobox [ref=e144]:
                - option "Buy" [selected]
                - option "Sell"
            - generic [ref=e145]:
              - generic [ref=e146]:
                - text: Order type
                - button "More information" [ref=e148]: ℹ️
              - combobox [ref=e149]:
                - option "Market"
                - option "Limit" [selected]
                - option "Stop-Loss (market on trigger)"
                - option "Stop-Limit"
                - option "GTT (Good Till Triggered)"
            - generic [ref=e150]:
              - generic [ref=e151]:
                - text: Product
                - button "More information" [ref=e153]: ℹ️
              - combobox [ref=e154]:
                - option "MIS (Intraday)"
                - option "CNC (Delivery)" [selected]
                - option "NRML (Carry)"
            - generic [ref=e155]:
              - generic [ref=e156]:
                - text: Quantity
                - button "More information" [ref=e158]: ℹ️
              - spinbutton [ref=e159]: "1"
            - generic [ref=e160]:
              - generic [ref=e161]:
                - text: Limit price
                - button "More information" [ref=e163]: ℹ️
              - spinbutton [ref=e164]: "0"
            - generic [ref=e165]:
              - generic [ref=e166]:
                - text: Stop-loss
                - button "More information" [ref=e168]: ℹ️
              - spinbutton [ref=e169]
            - generic [ref=e170]:
              - generic [ref=e171]:
                - text: Target
                - button "More information" [ref=e173]: ℹ️
              - spinbutton [ref=e174]
          - generic [ref=e175]:
            - generic [ref=e176]: Notes
            - textbox "Notes" [ref=e177]
          - generic [ref=e178]:
            - generic [ref=e179]:
              - generic [ref=e180]:
                - text: Trailing stop %
                - button "More information" [ref=e182]: ℹ️
              - spinbutton [ref=e183]: "2"
            - generic [ref=e184]:
              - generic [ref=e185]:
                - text: Cash allocation %
                - button "More information" [ref=e187]: ℹ️
              - spinbutton [ref=e188]: "10"
            - button "Apply trailing SL" [ref=e189] [cursor=pointer]
            - button "Use suggested qty 1 More information" [ref=e190] [cursor=pointer]:
              - text: Use suggested qty 1
              - button "More information" [ref=e192]: ℹ️
          - generic [ref=e193]:
            - generic [ref=e194]:
              - generic [ref=e195]: Current
              - strong [ref=e196]: "--"
            - generic [ref=e197]:
              - generic [ref=e198]: Estimated cost
              - strong [ref=e199]: ₹0.00
            - generic [ref=e200]:
              - generic [ref=e201]: Risk amount
              - strong [ref=e202]: ₹0.00
            - generic [ref=e203]:
              - generic [ref=e204]: Risk / Reward
              - strong [ref=e205]: "--"
          - paragraph [ref=e206]: "Account rule: avoid risking more than 2.0% per trade and prefer setups with at least 1:2 risk-reward."
          - generic [ref=e207]:
            - generic [ref=e208]: Risk 0.00% of account
            - button "Place paper order" [ref=e210] [cursor=pointer]
        - generic [ref=e211]:
          - generic [ref=e212]:
            - generic [ref=e213]:
              - paragraph [ref=e214]: Selected symbol
              - heading "INFY-EQ" [level=2] [ref=e215]
            - generic [ref=e216]:
              - generic [ref=e217]: Current ₹0.00
              - 'generic "Price source: NO_DATA • 9:35:45 AM" [ref=e218]': NO_DATA (stale)
          - generic [ref=e219]:
            - heading "No chart data" [level=2] [ref=e220]
            - paragraph [ref=e221]: Select a symbol or refresh the workspace to load candles.
        - generic [ref=e222]:
          - heading "No position selected" [level=2] [ref=e223]
          - paragraph [ref=e224]: Select a symbol with an active position to adjust stop-loss or target in the trade details panel.
```

# Test source

```ts
  42  |     const dbOrders = await tableDump(request, "paper_trading_orders");
  43  |     expect(dbOrders.rows.length).toBeGreaterThan(0);
  44  |     const createdOrder = dbOrders.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "BUY");
  45  |     expect(createdOrder).toBeDefined();
  46  |     // In test mode without live prices, orders may stay PENDING
  47  |     expect(["PENDING", "FILLED"]).toContain(createdOrder.status);
  48  | 
  49  |     // 4. Refresh the Positions tab to load fresh state
  50  |     await page.getByTestId("paper-tab-positions").click();
  51  |     await page.waitForTimeout(500); // Brief wait for API call
  52  | 
  53  |     // 5. Verify position appears in UI with lifecycle label
  54  |     await expect(page.getByText("INFY-EQ").first()).toBeVisible();
  55  |     // Position should have qty 10
  56  |     const positionRows = await page.locator('[data-testid="position-row"]').count();
  57  |     expect(positionRows).toBeGreaterThan(0);
  58  | 
  59  |     // 6. Check for price metadata (source, timestamp)
  60  |     const priceSourceText = page.locator('[data-testid="price-source"]');
  61  |     if (await priceSourceText.count() > 0) {
  62  |       const source = await priceSourceText.first().textContent();
  63  |       expect(source).toMatch(/LIVE|CACHE|FALLBACK/);
  64  |     }
  65  | 
  66  |     // 7. Reload the entire page (simulating browser refresh)
  67  |     await page.reload();
  68  |     await page.getByTestId("nav-paper-trading").click();
  69  |     await expect(page.getByTestId("paper-tab-positions")).toBeVisible();
  70  | 
  71  |     // 8. Verify position STILL appears after reload
  72  |     await page.getByTestId("paper-tab-positions").click();
  73  |     await page.waitForTimeout(500);
  74  |     // If PENDING, position won't show; if FILLED, it will show
  75  |     const posCountAfterReload = await page.locator('[data-testid="position-row"]').count();
  76  |     expect(posCountAfterReload).toBeGreaterThanOrEqual(0); // May be 0 if order is still PENDING
  77  | 
  78  |     // 9. Verify DB still shows the order after reload
  79  |     const dbOrdersAfterReload = await tableDump(request, "paper_trading_orders");
  80  |     const persistedOrder = dbOrdersAfterReload.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "BUY");
  81  |     expect(persistedOrder).toBeDefined();
  82  |     expect(["PENDING", "FILLED"]).toContain(persistedOrder.status);
  83  |   });
  84  | 
  85  |   test("open orders and history tabs are separated correctly", async ({ page, request }) => {
  86  |     await page.goto("/");
  87  |     await page.getByTestId("nav-paper-trading").click();
  88  | 
  89  |     // Place a BUY order
  90  |     const buyRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  91  |       data: {
  92  |         symbol: "INFY-EQ",
  93  |         side: "BUY",
  94  |         type: "MARKET",
  95  |         qty: 5,
  96  |         price: 100.0,
  97  |         notes: "open order test",
  98  |       },
  99  |     });
  100 |     expect(buyRes.ok()).toBeTruthy();
  101 | 
  102 |     // Place a SELL order (should close the position)
  103 |     const sellRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  104 |       data: {
  105 |         symbol: "INFY-EQ",
  106 |         side: "SELL",
  107 |         type: "MARKET",
  108 |         qty: 5,
  109 |         price: 105.0,
  110 |         notes: "close position",
  111 |       },
  112 |     });
  113 |     expect(sellRes.ok()).toBeTruthy();
  114 | 
  115 |     // 1. Check Open Orders tab (should be empty after both buy and sell)
  116 |     await page.getByTestId("paper-tab-orders").click();
  117 |     await page.waitForTimeout(500);
  118 |     const pendingOrderCount = await page.locator('[data-testid="pending-order-row"]').count();
  119 |     // After BUY + SELL, there should be no pending orders (both filled)
  120 |     expect(pendingOrderCount).toBe(0);
  121 | 
  122 |     // 2. Check History tab (should have both BUY and SELL)
  123 |     await page.getByTestId("paper-tab-history").click();
  124 |     await page.waitForTimeout(500);
  125 |     const historyRows = await page.locator('[data-testid="history-row"]').count();
  126 |     expect(historyRows).toBeGreaterThanOrEqual(2); // At least BUY and SELL
  127 | 
  128 |     // 3. Verify via DB that trade history contains both trades
  129 |     const dbHistory = await tableDump(request, "paper_trading_orders");
  130 |     const buyTrade = dbHistory.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "BUY");
  131 |     const sellTrade = dbHistory.rows.find((r: any) => r.symbol === "INFY-EQ" && r.side === "SELL");
  132 |     expect(buyTrade).toBeDefined();
  133 |     expect(sellTrade).toBeDefined();
  134 |   });
  135 | 
  136 |   test("lifecycle state and paused labels render from API response", async ({ page, request }) => {
  137 |     await page.goto("/");
  138 |     await page.getByTestId("nav-paper-trading").click();
  139 | 
  140 |     // Fetch the dashboard/account to check lifecycle metadata and balances
  141 |     const dashRes = await request.get(`${apiBaseURL}/paper-trading/dashboard`);
> 142 |     expect(dashRes.ok()).toBeTruthy();
      |                          ^ Error: expect(received).toBeTruthy()
  143 |     const dashboard = await dashRes.json();
  144 |     const account = dashboard.account;
  145 | 
  146 |     // Verify account has expected fields (updated API shape)
  147 |     expect(account).toHaveProperty("starting_balance");
  148 |     expect(account).toHaveProperty("balance");
  149 |     expect(account).toHaveProperty("realized_pnl");
  150 | 
  151 |     // Check Account tab for workspace display
  152 |     await page.getByTestId("paper-tab-account").click();
  153 |     await page.waitForTimeout(500);
  154 | 
  155 |     // Verify account info displays
  156 |     const balanceText = await page.locator('[data-testid="account-balance"]').textContent();
  157 |     expect(balanceText).toBeTruthy();
  158 |   });
  159 | 
  160 |   test("price source and staleness metadata display correctly", async ({ page, request }) => {
  161 |     await page.goto("/");
  162 |     await page.getByTestId("nav-paper-trading").click();
  163 | 
  164 |     // Place an order
  165 |     const orderRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  166 |       data: {
  167 |         symbol: "SBIN-EQ",
  168 |         side: "BUY",
  169 |         type: "MARKET",
  170 |         qty: 2,
  171 |         price: 500.0,
  172 |         notes: "price metadata test",
  173 |       },
  174 |     });
  175 |     expect(orderRes.ok()).toBeTruthy();
  176 | 
  177 |     // Fetch positions via the dedicated endpoint
  178 |     const posRes = await request.get(`${apiBaseURL}/paper-trading/positions`);
  179 |     expect(posRes.ok()).toBeTruthy();
  180 |     const positions = await posRes.json();
  181 | 
  182 |     // Verify position has price metadata
  183 |     if (positions.length > 0) {
  184 |       const pos = positions[0];
  185 |       expect(pos).toHaveProperty("price_source");
  186 |       expect(pos).toHaveProperty("price_fetched_at");
  187 |       expect(pos).toHaveProperty("is_price_stale");
  188 |       expect(["LIVE", "CACHE", "FALLBACK"]).toContain(pos.price_source);
  189 |     }
  190 | 
  191 |     // Also check open orders endpoint
  192 |     const ordersRes = await request.get(`${apiBaseURL}/paper-trading/orders/pending`);
  193 |     expect(ordersRes.ok()).toBeTruthy();
  194 |     const pendingOrders = await ordersRes.json();
  195 |     // Should be empty if all orders filled
  196 |     expect(Array.isArray(pendingOrders)).toBe(true);
  197 | 
  198 |     // Check history endpoint
  199 |     const historyRes = await request.get(`${apiBaseURL}/paper-trading/orders/history`);
  200 |     expect(historyRes.ok()).toBeTruthy();
  201 |     const history = await historyRes.json();
  202 |     expect(Array.isArray(history)).toBe(true);
  203 | 
  204 |     // Check trades endpoint
  205 |     const tradesRes = await request.get(`${apiBaseURL}/paper-trading/trades`);
  206 |     expect(tradesRes.ok()).toBeTruthy();
  207 |     const trades = await tradesRes.json();
  208 |     expect(Array.isArray(trades)).toBe(true);
  209 |   });
  210 | 
  211 |   test("dashboard endpoint aggregates all data correctly", async ({ request }) => {
  212 |     // Place orders to create a dashboard state
  213 |     const orderRes = await request.post(`${apiBaseURL}/paper-trading/orders`, {
  214 |       data: {
  215 |         symbol: "INFY-EQ",
  216 |         side: "BUY",
  217 |         type: "MARKET",
  218 |         qty: 3,
  219 |         price: 100.0,
  220 |         notes: "dashboard test buy",
  221 |       },
  222 |     });
  223 |     expect(orderRes.ok()).toBeTruthy();
  224 | 
  225 |     // Fetch the full dashboard
  226 |     const dashRes = await request.get(`${apiBaseURL}/paper-trading/dashboard`);
  227 |     expect(dashRes.ok()).toBeTruthy();
  228 |     const dashboard = await dashRes.json();
  229 | 
  230 |     // Verify dashboard has all required sections
  231 |     expect(dashboard).toHaveProperty("workspace");
  232 |     expect(dashboard).toHaveProperty("positions");
  233 |     expect(dashboard).toHaveProperty("pending_orders");
  234 |     expect(dashboard).toHaveProperty("order_history");
  235 |     expect(dashboard).toHaveProperty("trades");
  236 | 
  237 |     // Verify positions in dashboard match dedicated endpoint
  238 |     const posRes = await request.get(`${apiBaseURL}/paper-trading/positions`);
  239 |     const positions = await posRes.json();
  240 |     expect(dashboard.positions.length).toBe(positions.length);
  241 | 
  242 |     // Verify history in dashboard matches dedicated endpoint
```