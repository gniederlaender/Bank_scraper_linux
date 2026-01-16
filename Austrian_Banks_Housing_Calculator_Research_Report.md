# Austrian Banks Housing Loan Calculator Research Report

## Executive Summary

This report analyzes the housing loan calculators of four major Austrian banks: BAWAG, Bank99, Erste Bank, and Raiffeisen Bank. The primary goal was to identify URLs and determine the optimal data extraction approach (API vs. web scraping).

**Key Findings:**
- **No public APIs available** for any of the four banks' housing loan calculators
- All calculators are **web-based interfaces** requiring manual interaction
- **Web scraping** is the only viable automated approach
- **Legal compliance** is a major consideration for all banks
- **Technical complexity** varies significantly between banks

## Bank-by-Bank Analysis

### 1. BAWAG Bank

**Calculator URL:** https://www.bawag.at/bawag/privatkunden/services-infos/rechner/kreditrechner/

**Description:** 
- Standard online credit calculator
- Estimates monthly loan payments
- Input parameters: loan amount, term duration
- Interactive interface with real-time calculations

**Technical Assessment:**
- **API Available:** ❌ No public API
- **JavaScript Dependency:** ⚠️ High - Dynamic content rendering
- **Form Complexity:** 🟡 Medium - Standard input fields
- **Anti-Scraping Measures:** 🟡 Unknown - Standard website

**Data Extraction Approach:** Web scraping with JavaScript rendering (Selenium/Puppeteer required)

---

### 2. Bank99

**Calculator URL:** https://bank99.at/wohnfinanzierung/wohnkredit99

**Description:**
- Specialized housing loan calculator ("Wohnkredit99")
- Input parameters: property price, own funds, interest type (fixed/variable), loan term
- Multi-parameter calculator with interactive elements

**Technical Assessment:**
- **API Available:** ❌ No public API  
- **JavaScript Dependency:** ⚠️ High - Interactive sliders and dynamic calculations
- **Form Complexity:** 🔴 High - Multiple interactive elements, sliders
- **Anti-Scraping Measures:** 🟡 Unknown - Standard website

**Data Extraction Approach:** Web scraping with advanced interaction handling (Selenium recommended)

---

### 3. Erste Bank

**Calculator URL:** https://www.sparkasse.at/sgruppe/privatkunden/wohnen-finanzieren/wohnfinanzierung/wohnkreditrechner

**Description:**
- Comprehensive housing loan calculator
- Multi-step process (4 steps mentioned)
- Includes subsidies calculation and household budget overview
- Most complex calculator of the four banks

**Technical Assessment:**
- **API Available:** ❌ No public API
- **JavaScript Dependency:** ⚠️ High - Multi-step process, AJAX requests likely
- **Form Complexity:** 🔴 Very High - Multi-step wizard, session management
- **Anti-Scraping Measures:** 🟡 Unknown - Enterprise-grade website

**Data Extraction Approach:** Web scraping with complex navigation flow (Selenium with session handling)

---

### 4. Raiffeisen Bank

**Calculator URL:** https://www.raiffeisen.at/de/immobilien/rechner-tools.html

**Description:**
- Multiple calculators available on single page
- Housing loan calculator among various financial tools
- Standard parameter inputs for loan calculations

**Technical Assessment:**
- **API Available:** ❌ No public API
- **JavaScript Dependency:** 🟡 Medium - Standard calculator functionality
- **Form Complexity:** 🟡 Medium - Multiple calculators on one page
- **Anti-Scraping Measures:** 🟡 Unknown - Standard website

**Data Extraction Approach:** Web scraping with calculator identification and selection

## Technical Implementation Approaches

### Option 1: Web Scraping (Only Viable Option)

#### Recommended Technology Stack:
- **Python** with Selenium WebDriver
- **Alternative:** Node.js with Puppeteer
- **Backup:** BeautifulSoup + Requests (limited functionality)

#### Implementation Considerations:

**1. JavaScript Rendering Requirements:**
- All calculators require JavaScript execution
- Headless browser automation is mandatory
- Real browser simulation needed for accurate results

**2. Technical Challenges:**
- **Dynamic content loading** - Results generated client-side
- **Session management** - Multi-step processes (especially Erste Bank)
- **Form interaction complexity** - Sliders, dropdowns, multi-step wizards
- **Rate limiting** - Avoid overwhelming bank servers
- **User agent rotation** - Mimic legitimate browser behavior

**3. Data Extraction Workflow:**
```
1. Initialize headless browser (Chrome/Firefox)
2. Navigate to calculator URL
3. Wait for page load and JavaScript initialization
4. Input loan parameters (amount, term, rate, etc.)
5. Trigger calculation (button clicks, form submissions)
6. Wait for results rendering
7. Extract calculated data (payments, rates, fees)
8. Clean and structure data
9. Store results
```

#### Bank-Specific Implementation Notes:

**BAWAG:**
- Straightforward form interaction
- Single-step calculation process
- Focus on input field automation and result extraction

**Bank99:**
- Complex interactive elements (sliders)
- Multiple parameter dependencies
- Requires advanced element interaction (drag operations)

**Erste Bank:**
- Multi-step wizard navigation
- Session state management critical
- May require cookie handling and form progression
- Highest implementation complexity

**Raiffeisen:**
- Multiple calculators on single page
- Calculator selection logic needed
- Standard form interaction afterwards

## Legal and Compliance Considerations

### Terms of Service Analysis:
⚠️ **Critical:** All banks' terms of service must be reviewed before implementation

**Potential Legal Issues:**
- Unauthorized data extraction
- Terms of service violations
- Intellectual property concerns
- Rate limiting violations leading to service disruption

**Recommended Actions:**
1. **Contact banks directly** to request API access or data sharing agreements
2. **Review terms of service** thoroughly for each bank
3. **Implement respectful scraping** with appropriate delays and limits
4. **Consider legal consultation** before large-scale implementation

## Alternative Approaches

### 1. Direct Bank Contact
- **Pros:** Legal compliance, potential API access, official support
- **Cons:** Time-consuming, potential rejection, limited control
- **Recommendation:** Attempt first before scraping implementation

### 2. Manual Data Collection
- **Pros:** Complete legal compliance, no technical complexity
- **Cons:** Labor-intensive, limited scalability, prone to human error
- **Use case:** Limited scenarios, validation of automated results

### 3. Third-Party Financial Data Providers
- **Pros:** Legal access, standardized APIs, multiple bank coverage
- **Cons:** Cost, may not include all target banks, limited customization
- **Research needed:** Investigate Austrian financial data aggregators

## Implementation Timeline and Effort Estimation

### Phase 1: Legal and Preparation (2-3 weeks)
- Contact banks for official API access
- Legal review of terms of service
- Technical architecture planning

### Phase 2: Technical Development (4-6 weeks)
- **Week 1-2:** BAWAG implementation (simplest)
- **Week 3-4:** Bank99 and Raiffeisen implementation
- **Week 5-6:** Erste Bank implementation (most complex)

### Phase 3: Testing and Refinement (2-3 weeks)
- Comprehensive testing across all calculators
- Error handling and edge case management
- Performance optimization and rate limiting
- Data validation and quality assurance

### Phase 4: Deployment and Monitoring (1-2 weeks)
- Production deployment
- Monitoring setup for failures and changes
- Maintenance documentation

**Total Estimated Timeline:** 9-14 weeks

## Risk Assessment

### High Risks:
- **Legal action** from banks for unauthorized scraping
- **IP blocking** due to automated access
- **Frequent maintenance** required due to website changes
- **Data accuracy issues** from dynamic content changes

### Medium Risks:
- **Performance degradation** from complex JavaScript rendering
- **Scalability limitations** from browser automation overhead
- **False positive results** from incorrect form interactions

### Mitigation Strategies:
- Implement comprehensive logging and monitoring
- Create fallback mechanisms for failed extractions
- Regular validation against known manual calculations
- Gradual rollout with extensive testing

## Recommendations

### Primary Recommendation: **Contact Banks First**
Before implementing any scraping solution, reach out to each bank to:
1. Request official API access
2. Seek permission for data extraction
3. Explore partnership opportunities
4. Understand their data policies

### Secondary Recommendation: **Phased Web Scraping Implementation**
If bank contact is unsuccessful:
1. Start with **BAWAG** (simplest implementation)
2. Implement comprehensive **legal compliance measures**
3. Use **conservative rate limiting** (5-10 second delays between requests)
4. Implement **robust error handling** and monitoring
5. Plan for **regular maintenance** and updates

### Technical Architecture Recommendation:
- **Python + Selenium** for maximum flexibility and community support
- **Docker containerization** for consistent environment
- **Proxy rotation** to minimize IP blocking risk
- **Database storage** with versioning for historical data
- **API layer** to abstract scraping complexity from consumers

## Next Steps

1. **Immediate Actions:**
   - Contact bank representatives to inquire about API access
   - Conduct legal review of terms of service for all four banks
   - Set up development environment for testing

2. **Development Preparation:**
   - Create test scenarios with various loan parameters
   - Design data structure for storing results
   - Plan monitoring and alerting system

3. **Implementation Priority:**
   - Begin with BAWAG (lowest complexity)
   - Document lessons learned for subsequent banks
   - Create reusable components for common functionality

---

**Report Date:** September 28, 2025  
**Status:** Ready for Implementation Planning  
**Next Review:** After bank contact attempts and legal review completion