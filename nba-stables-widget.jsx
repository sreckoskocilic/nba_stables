// NBA Stables Widget
// Change the URL below to your Render URL
const API_URL = "https://nba-stables.onrender.com";

export const refreshFrequency = 60000; // Refresh every 60 seconds

export const command = `curl -s ${API_URL}/api/scoreboard`;

export const className = `
  top: 20px;
  right: 20px;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  color: #fff;
  background: rgba(10, 10, 15, 0.85);
  backdrop-filter: blur(10px);
  padding: 16px;
  border-radius: 12px;
  width: 280px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  border: 1px solid rgba(255,255,255,0.1);
`;

const headerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: '12px',
  paddingBottom: '10px',
  borderBottom: '1px solid rgba(255,255,255,0.1)'
};

const titleStyle = {
  fontWeight: '600',
  fontSize: '14px',
  display: 'flex',
  alignItems: 'center',
  gap: '6px'
};

const dateStyle = {
  fontSize: '11px',
  color: '#888'
};

const gameStyle = {
  marginBottom: '10px',
  padding: '10px',
  background: 'rgba(255,255,255,0.05)',
  borderRadius: '8px'
};

const teamRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: '4px'
};

const teamNameStyle = {
  fontSize: '12px',
  fontWeight: '500'
};

const scoreStyle = {
  fontSize: '14px',
  fontWeight: '700',
  color: '#ff6b35'
};

const statusStyle = {
  fontSize: '10px',
  color: '#888',
  textTransform: 'uppercase',
  marginTop: '6px'
};

const leaderStyle = {
  fontSize: '10px',
  color: '#666',
  marginTop: '4px'
};

const emptyStyle = {
  textAlign: 'center',
  padding: '20px',
  color: '#666'
};

export const render = ({ output }) => {
  try {
    const data = JSON.parse(output);

    if (!data.games || data.games.length === 0) {
      return (
        <div>
          <div style={headerStyle}>
            <span style={titleStyle}>🏀 NBA Stables</span>
          </div>
          <div style={emptyStyle}>No games today</div>
        </div>
      );
    }

    return (
      <div>
        <div style={headerStyle}>
          <span style={titleStyle}>🏀 NBA Live</span>
          <span style={dateStyle}>{data.date}</span>
        </div>
        {data.games.map((game, i) => (
          <div key={i} style={gameStyle}>
            <div style={teamRowStyle}>
              <span style={teamNameStyle}>{game.awayTeam.tricode}</span>
              <span style={scoreStyle}>{game.awayTeam.score}</span>
            </div>
            <div style={teamRowStyle}>
              <span style={teamNameStyle}>{game.homeTeam.tricode}</span>
              <span style={scoreStyle}>{game.homeTeam.score}</span>
            </div>
            <div style={statusStyle}>{game.status}</div>
            <div style={leaderStyle}>
              ⭐ {game.homeTeam.leader.name} {game.homeTeam.leader.points}pts
            </div>
          </div>
        ))}
      </div>
    );
  } catch (e) {
    return (
      <div>
        <div style={headerStyle}>
          <span style={titleStyle}>🏀 NBA Stables</span>
        </div>
        <div style={emptyStyle}>Loading...</div>
      </div>
    );
  }
};
