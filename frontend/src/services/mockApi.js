/**
 * Mock API — Realistic simulation with keyword-matched responses
 * 
 * Responses are mapped to questions by keyword matching so the demo
 * feels coherent (ask about sales → get sales data, ask about Tesla → get comparison).
 */

const RESPONSES = {
  top_selling: `Based on the sales data analysis, here are the key findings:\n\n**Top 5 Selling Vehicles:**\n\n| Rank | Company | Model | Total Sales |\n|------|---------|-------|------------|\n| 1 | Toyota | XKR | 52,340 |\n| 2 | Tesla | ELV | 48,920 |\n| 3 | BMW | GTX | 41,105 |\n| 4 | Hyundai | PRO | 38,760 |\n| 5 | Tata | NEX | 35,440 |\n\nToyota leads the market with **52,340 units sold**, primarily driven by strong performance in the SUV segment across India and the USA regions. The top 5 vehicles account for 67% of total sales volume.`,

  sales_region: `Here's the regional sales breakdown for the last quarter:\n\n📊 **Sales by Region:**\n\n| Region | Revenue | Share | YoY Growth |\n|--------|---------|-------|------------|\n| India | ₹2.4B | 42% | +18% |\n| USA | $1.8B | 31% | +9% |\n| Europe | €1.5B | 27% | +11% |\n\nIndia continues to be the **strongest market**, with a 18% year-over-year growth driven primarily by the SUV and Hatchback segments. Electric vehicle adoption is highest in Europe at 34%.\n\n**Top Cities:**\n1. Mumbai — ₹420M\n2. New York — $310M\n3. Berlin — €280M`,

  customer_rating: `The average customer rating across all vehicle segments is **3.72 out of 5.0**.\n\n**Rating Breakdown by Segment:**\n\n| Segment | Rating | Sample Size | Trend |\n|---------|--------|-------------|-------|\n| Sedan | 3.89 ★ | 18,420 | ↑ +0.2 |\n| SUV | 3.71 ★ | 24,105 | ↑ +0.1 |\n| Hatchback | 3.56 ★ | 12,890 | → 0.0 |\n\n**Key Insights:**\n1. Premium variants consistently score **0.4 points higher** than Base variants\n2. Automatic transmission vehicles have 12% higher satisfaction\n3. Electric vehicles show the highest rating improvement trend (+0.3 YoY)\n4. Customer feedback labeled "good" accounts for 62% of all reviews`,

  tesla_toyota: `Comparing **Tesla vs Toyota** across key metrics:\n\n| Metric | Tesla | Toyota | Winner |\n|--------|-------|--------|--------|\n| Avg Price | $68,500 | $42,300 | Toyota (value) |\n| Total Sales | 48,920 | 52,340 | Toyota |\n| Avg Rating | 4.1 ★ | 3.8 ★ | Tesla |\n| Top Speed | 245 km/h | 210 km/h | Tesla |\n| Avg Mileage | N/A (EV) | 18.5 km/l | — |\n| CO2 Emission | 0 g/km | 142 g/km | Tesla |\n| Safety Rating | 4.8 | 4.5 | Tesla |\n| Autonomous Level | 3.2 | 1.8 | Tesla |\n\n**Summary**: Toyota leads in volume but Tesla commands a **premium positioning** with higher customer satisfaction and zero emissions. Tesla's autonomous features (Level 3+) are a key differentiator in the $60K+ segment.`,

  sensor_anomaly: `I found **847 anomaly events** in the sensor data for the selected time period.\n\n🔴 **Critical Anomalies:**\n\n| Type | Count | Affected Vehicles |\n|------|-------|---------|\n| Temperature spikes (>150°C) | 312 | 45 |\n| RPM irregularities | 189 | 32 |\n| Battery voltage drops (<11.5V) | 98 | 18 |\n| Fault code P001 | 156 | 28 |\n| Fault code P002 | 92 | 15 |\n\n⚠️ **Vehicles requiring immediate attention:**\n- Vehicle #23401 — 12 temperature spikes in 24 hours\n- Vehicle #67829 — Consistent oil temperature above threshold\n- Vehicle #11204 — Recurring fault code P002\n\n> **Recommendation**: Schedule diagnostic checks for the flagged vehicles and investigate the temperature spike cluster in the Tesla ELV fleet.`,

  revenue_trends: `Here's the quarterly revenue trend analysis:\n\n**Revenue by Quarter (FY 2024-25):**\n\n| Quarter | Revenue | Growth | Top Segment |\n|---------|---------|--------|-------------|\n| Q1 | ₹3.2B | — | SUV |\n| Q2 | ₹3.8B | +18.7% | SUV |\n| Q3 | ₹4.1B | +7.9% | Sedan |\n| Q4 | ₹4.6B | +12.2% | SUV |\n\n**Total FY Revenue: ₹15.7B** (+14.2% YoY)\n\nKey growth drivers:\n1. **SUV segment** grew 22% — highest among all segments\n2. **Electric vehicles** contributed ₹2.1B (13.4% of total)\n3. **India market** expanded 18%, outpacing USA (+9%) and Europe (+11%)\n\nProjection for next quarter: ₹4.9B based on current order pipeline.`,

  fuel_type: `Based on the data, here's the fuel type distribution analysis:\n\n**Sales by Fuel Type:**\n\n| Fuel Type | Sales | Market Share | YoY Change |\n|-----------|-------|-------------|------------|\n| Petrol | 1.8M | 36% | -4.2% |\n| Diesel | 1.2M | 24% | -8.1% |\n| Electric | 1.1M | 22% | +34.5% |\n| Hybrid | 0.9M | 18% | +21.3% |\n\n**Key Trend**: Electric vehicles are on track to become the **#2 fuel type by next year**, overtaking Diesel. Hybrid vehicles are also gaining share rapidly.\n\nThe average price premium for EVs over petrol equivalents has dropped from 45% to 28% in the last year, driving faster adoption.`,

  price_analysis: `Here's the vehicle pricing analysis across segments:\n\n**Average Price by Segment:**\n\n| Segment | Avg Price | Min | Max | Median |\n|---------|-----------|-----|-----|--------|\n| SUV | ₹12.8L | ₹6.2L | ₹45L | ₹10.5L |\n| Sedan | ₹9.4L | ₹4.8L | ₹32L | ₹7.8L |\n| Hatchback | ₹5.6L | ₹3.2L | ₹12L | ₹4.9L |\n\n**Price Trends:**\n- Premium variants command a **38% price premium** over Base\n- Electric vehicles average **28% higher** than petrol equivalents\n- Prices have increased 6.2% YoY across all segments\n\n> The sweet spot for highest sales volume is the ₹8L–₹12L range, which accounts for 41% of all transactions.`,

  default: `Here's a summary of the data lake overview:\n\n**Database Statistics:**\n\n| Table | Records | Columns | Last Updated |\n|-------|---------|---------|-------------|\n| Vehicles | 100,000 | 34 | Today |\n| Customers | 200,000 | 13 | Today |\n| Sales | 5,000,000 | 15 | Today |\n| Sensors | 5,000,000 | 20 | Today |\n\n**Quick Insights:**\n- 6 vehicle companies tracked: Toyota, Ford, Tesla, BMW, Hyundai, Tata\n- 3 regions: India, USA, Europe\n- Vehicle segments: SUV, Sedan, Hatchback\n- Fuel types: Petrol, Diesel, Electric, Hybrid\n\nYou can ask me about sales trends, vehicle comparisons, customer ratings, sensor anomalies, regional breakdowns, or any other data question!`,
};

/**
 * Match a user message to the most relevant response by keyword analysis.
 */
function matchResponse(message) {
  const msg = message.toLowerCase();

  if (msg.includes('top') && (msg.includes('sell') || msg.includes('car') || msg.includes('vehicle'))) {
    return RESPONSES.top_selling;
  }
  if ((msg.includes('region') || msg.includes('country') || msg.includes('india') || msg.includes('usa') || msg.includes('europe')) && (msg.includes('sale') || msg.includes('break') || msg.includes('show'))) {
    return RESPONSES.sales_region;
  }
  if (msg.includes('rating') || msg.includes('review') || msg.includes('satisfaction') || msg.includes('feedback')) {
    return RESPONSES.customer_rating;
  }
  if ((msg.includes('tesla') && msg.includes('toyota')) || msg.includes('compare') || msg.includes('versus') || msg.includes('vs')) {
    return RESPONSES.tesla_toyota;
  }
  if (msg.includes('anomal') || msg.includes('sensor') || msg.includes('fault') || msg.includes('temperature') || msg.includes('diagnostic')) {
    return RESPONSES.sensor_anomaly;
  }
  if (msg.includes('revenue') || msg.includes('trend') || msg.includes('quarter') || msg.includes('growth')) {
    return RESPONSES.revenue_trends;
  }
  if (msg.includes('fuel') || msg.includes('electric') || msg.includes('petrol') || msg.includes('diesel') || msg.includes('hybrid') || msg.includes('ev')) {
    return RESPONSES.fuel_type;
  }
  if (msg.includes('price') || msg.includes('cost') || msg.includes('expensive') || msg.includes('cheap') || msg.includes('afford')) {
    return RESPONSES.price_analysis;
  }
  if (msg.includes('sale') || msg.includes('sold') || msg.includes('selling')) {
    return RESPONSES.top_selling;
  }

  return RESPONSES.default;
}

// ---- Mock STT transcriptions mapped to chip text ----
const MOCK_TRANSCRIPTIONS = [
  'Show me the top selling cars this quarter',
  'What is the average customer rating by segment',
  'Compare Tesla versus Toyota sales performance',
  'Show the sales breakdown by region',
  'Are there any sensor anomalies in the fleet data',
  'What are the revenue trends for this year',
  'Show fuel type distribution in sales',
];

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Mock STT
 */
export async function mockTranscribeAudio(audioBlob) {
  await delay(randomBetween(1000, 2000));
  return {
    text: pickRandom(MOCK_TRANSCRIPTIONS),
    confidence: 0.88 + Math.random() * 0.11,
    language: 'en',
  };
}

/**
 * Mock streaming — keyword-matched response, token-by-token
 */
export async function mockStreamMessage(message, conversationId, onToken, onComplete, onError, controller = {}) {
  try {

    await delay(randomBetween(300, 600));
    if (controller.cancelled) return;

    // Get the RELEVANT response for this question
    const response = matchResponse(message);
    const tokens = response.split('');

    for (let i = 0; i < tokens.length; i++) {
      if (controller.cancelled) return;

      const baseDelay = randomBetween(6, 22);
      const isPause = Math.random() < 0.006;
      const pauseDelay = isPause ? randomBetween(150, 400) : 0;
      const isNewline = tokens[i] === '\n';
      const newlineDelay = isNewline ? randomBetween(10, 35) : 0;

      await delay(baseDelay + pauseDelay + newlineDelay);
      if (controller.cancelled) return;
      onToken(tokens[i]);
    }

    if (!controller.cancelled) onComplete();
  } catch (err) {
    if (!controller.cancelled) onError(err);
  }
}

/**
 * Mock chat (non-streaming)
 */
export async function mockSendMessage(message, conversationId) {
  await delay(randomBetween(600, 1200));
  return {
    response: matchResponse(message),
    conversation_id: conversationId,
  };
}

export async function mockCheckHealth() {
  await delay(randomBetween(100, 300));
  return { status: 'healthy', mock: true };
}

export async function mockGetHistory(conversationId) {
  await delay(randomBetween(200, 400));
  return { conversations: [], source: 'mock' };
}

export async function mockLogin(email, password) {
  await delay(randomBetween(800, 1500));
  
  // Default mock user
  const mockUser = { 
    id: '1', 
    name: 'Neural User', 
    email: email || 'user@voxa.ai',
    role: 'user'
  };

  if (password === 'error') throw new Error('Invalid credentials');
  
  return {
    user: mockUser,
    access_token: 'mock-jwt-token',
  };
}

export async function mockSignup(userData) {
  await delay(randomBetween(1000, 2000));
  return {
    user: { id: '1', ...userData },
    access_token: 'mock-jwt-token',
  };
}

export async function mockGetMe() {
  await delay(randomBetween(200, 500));
  return { id: '1', name: 'Neural User', email: 'user@voxa.ai' };
}

export async function mockRequestPasswordReset(email) {
  await delay(randomBetween(800, 1500));
  if (email === 'error@example.com') throw new Error('Email not found');
  return { message: 'Reset link sent to your email' };
}

export async function mockResetPassword(token, newPassword) {
  await delay(randomBetween(800, 1500));
  if (token === 'invalid') throw new Error('Invalid or expired token');
  return { message: 'Password reset successful' };
}
