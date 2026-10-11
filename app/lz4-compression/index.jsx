// LZ4 Compression: native PS5 app for the LZ4 Compression engine (payload).
import {useCallback, useEffect, useRef, useState} from 'react';
import {AppRegistry, BackHandler, Controller, View, useFocus, useNavigationEvents} from '@ps5-react/core';
import {api, startEngine} from './api.js';
import {ACTION_PAGES, formatBytes, gameId, stabilize} from './model.js';
import {GamePage, Home} from './screens.jsx';
import {
  AboutPage, CompressPage, DeletePage, DoneOverlay, HistoryPage, Lz4Page, MovePage, Offline, PowerPage,
  Splash, Toast, UncompressPage,
} from './pages.jsx';

const JOB_POLL_MS = 1000;
const LIST_POLL_MS = 6000;

// A light tick on every focus move, a firmer one on presses, like Overdrive.
function useHaptics() {
  useNavigationEvents(event => {
    try {
      if (event.type === 'move') Controller.vibrate(0.22, 24);
      else if (event.type === 'press' && event.handled) Controller.vibrate(0.4, 36);
      else if (event.type === 'blocked') Controller.vibrate(0.12, 16);
    } catch (err) {
      // Vibration is a nicety; never let it break navigation.
    }
  });
}

function freeSpaceText(games) {
  const internal = games.find(game => String(game.sourcePath || '').startsWith('/data/') && game.freeBytes > 0);
  return internal ? `Internal SSD  ${formatBytes(internal.freeBytes)} free` : '';
}

function lowSpaceText(err) {
  const data = err.data || {};
  if (data.lowSpace) {
    const extra = data.extraBytes ? formatBytes(data.extraBytes) : '';
    return extra ? `Not enough free space: ${extra} more is needed.` : 'Not enough free space.';
  }
  return err.message || 'The engine refused the request.';
}

function App() {
  const [phase, setPhase] = useState('connecting');
  const [splashText, setSplashText] = useState('Connecting to the engine');
  const [offlineText, setOfflineText] = useState('');
  const [version, setVersion] = useState('');
  const [games, setGames] = useState([]);
  const [history, setHistory] = useState([]);
  const [job, setJob] = useState({busy: false});
  const [stack, setStack] = useState([{name: 'home'}]);
  const [toast, setToast] = useState(null);
  const [done, setDone] = useState(null);
  const lastActive = useRef('');
  const toastTimer = useRef(0);
  const {focus} = useFocus();
  useHaptics();

  const showToast = useCallback((title, text, error) => {
    setToast({title, text, error});
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), error ? 6000 : 3000);
  }, []);

  const refreshAll = useCallback(async () => {
    const [gameData, historyData, jobData] = await Promise.all([
      api.games(), api.history(), api.job().catch(() => null),
    ]);
    setGames(previous => stabilize(previous, gameData.games || []));
    setHistory(historyData.history || []);
    if (jobData) setJob(jobData);
  }, []);

  const connect = useCallback(async (startIt) => {
    setPhase('connecting');
    const started = Date.now();
    const ready = async () => {
      try {
        const status = await api.status();
        setVersion(status.version || '');
        return true;
      } catch (err) {
        return false;
      }
    };
    let ok = await ready();
    if (!ok && startIt !== false) {
      setSplashText('Starting the engine');
      try {
        await startEngine();
      } catch (err) {
        // Payload Manager isn't there; the offline screen explains.
      }
      for (let i = 0; i < 20 && !ok; i++) {
        await new Promise(resolve => setTimeout(resolve, 750));
        ok = await ready();
      }
    }
    if (!ok) {
      setOfflineText('');
      setPhase('offline');
      return;
    }
    setSplashText('Scanning games');
    try {
      await refreshAll();
    } catch (err) {
      setOfflineText(err.message || '');
      setPhase('offline');
      return;
    }
    const wait = Math.max(0, 900 - (Date.now() - started));
    setTimeout(() => setPhase('ready'), wait);
  }, [refreshAll]);

  useEffect(() => { connect(true); }, [connect]);

  // Job every second; games and history every few seconds, and right away when a job ends.
  useEffect(() => {
    if (phase !== 'ready') return undefined;
    let tick = 0;
    const timer = setInterval(async () => {
      tick++;
      try {
        const jobData = await api.job();
        setJob(jobData);
        const active = String(jobData.activeId || '');
        const previous = lastActive.current;
        lastActive.current = active;
        const finished = previous && active !== previous;
        if (finished || tick % (jobData.busy ? 3 : Math.round(LIST_POLL_MS / JOB_POLL_MS)) === 0) {
          await refreshAll();
        }
        if (finished) {
          const data = await api.history();
          const op = (data.history || []).find(item => String(item.id) === previous);
          if (op && op.status !== 'cancelled') setDone(op);
        }
      } catch (err) {
        // The engine went away (closed from the web page, or crashed).
      }
    }, JOB_POLL_MS);
    return () => clearInterval(timer);
  }, [phase, refreshAll]);

  const push = useCallback(entry => setStack(previous => [...previous, entry]), []);
  const pop = useCallback(() => setStack(previous => (previous.length > 1 ? previous.slice(0, -1) : previous)), []);
  const depth = stack.length - 1;

  // Give focus back to the screen that is uncovered.
  const lastDepth = useRef(0);
  useEffect(() => {
    if (depth < lastDepth.current) focus(depth === 0 ? 'screen-home' : 'screen-' + depth);
    lastDepth.current = depth;
  }, [depth, focus]);

  const top = stack[stack.length - 1];
  const gameOf = entry => (entry && entry.id ? games.find(game => gameId(game) === entry.id) : null);

  const openGame = useCallback(id => { if (id) push({name: 'game', id}); }, [push]);

  // Start a job from an action page, then go back to the game page to watch it.
  const startFrom = useCallback(async (request, label) => {
    try {
      await request();
      showToast(`${label} started`, '');
      pop();
      refreshAll().catch(() => {});
    } catch (err) {
      showToast("Couldn't start", lowSpaceText(err), true);
    }
  }, [pop, refreshAll, showToast]);

  const onAction = useCallback(async action => {
    const entry = stack[stack.length - 1];
    const game = gameOf(entry);
    if (!game) return;
    const page = ACTION_PAGES[action];
    if (page) {
      push({name: page, id: entry.id, action});
      return;
    }
    try {
      if (action === 'update-ampr') await api.updateAmpr(game);
      else await api.run(action, game);
      showToast('Started', game.name || game.titleId);
      refreshAll().catch(() => {});
    } catch (err) {
      showToast("Couldn't start", lowSpaceText(err), true);
    }
  }, [stack, games, push, refreshAll, showToast]);

  const cancelJob = useCallback(async () => {
    try {
      await api.cancelJob();
      showToast('Cancelling', 'The job stops at the next safe point.');
    } catch (err) {
      showToast("Couldn't cancel", err.message, true);
    }
  }, [showToast]);

  const cancelQueued = useCallback(async id => {
    try {
      await api.cancelQueued(id);
      refreshAll().catch(() => {});
    } catch (err) {
      showToast("Couldn't cancel", err.message, true);
    }
  }, [refreshAll, showToast]);

  const stop = useCallback(async stopEngine => {
    if (stopEngine !== false) {
      try {
        await api.shutdown();
      } catch (err) {
        // Closing anyway.
      }
    }
    BackHandler.exitApp();
  }, []);

  if (phase === 'connecting') return <Splash status={splashText} />;
  if (phase === 'offline') {
    return <Offline message={offlineText} onStart={() => connect(true)} onRetry={() => connect(false)} />;
  }

  const pages = stack.slice(1).map((entry, index) => {
    const level = index + 1;
    const covered = level < depth || !!done;
    const hide = level < depth;
    const game = gameOf(entry);
    const common = {key: `${level}-${entry.name}`, depth: level, covered, hide, onBack: pop};
    if (entry.name === 'game') {
      return <GamePage {...common} game={game} job={job} version={version} onAction={onAction}
        onCancel={cancelJob} onCancelQueued={cancelQueued} />;
    }
    if (entry.name === 'history') return <HistoryPage {...common} history={history} />;
    if (entry.name === 'about') return <AboutPage {...common} version={version} />;
    if (entry.name === 'power') return <PowerPage {...common} onStop={stop} />;
    if (!game) return null;
    if (entry.name === 'compress') return <CompressPage {...common} game={game} action={entry.action} onStart={startFrom} />;
    if (entry.name === 'lz4') {
      return <Lz4Page {...common} game={game} mode={entry.action === 'lz4-unpack' ? 'unpack' : 'pack'} onStart={startFrom} />;
    }
    if (entry.name === 'uncompress') return <UncompressPage {...common} game={game} onStart={startFrom} />;
    if (entry.name === 'move') return <MovePage {...common} game={game} copy={entry.action === 'copy-to'} onStart={startFrom} />;
    if (entry.name === 'delete') {
      return <DeletePage {...common} game={game} onStart={(request, label) => {
        startFrom(request, label).then(() => setStack([{name: 'home'}]));
      }} />;
    }
    return null;
  });

  const doneGame = done ? games.find(game => game.titleId === done.titleId) : null;
  return (
    <View className="w-screen h-screen bg-ink">
      <Home games={games} history={history} job={job} version={version} freeText={freeSpaceText(games)}
        covered={depth > 0 || !!done} hide={depth > 0} onOpen={openGame}
        onHistory={() => push({name: 'history'})} onAbout={() => push({name: 'about'})} onPower={() => push({name: 'power'})} />
      {pages}
      {done ? <DoneOverlay op={done} game={doneGame} onClose={() => {
        setDone(null);
        setTimeout(() => focus(depth === 0 ? 'screen-home' : 'screen-' + depth), 0);
      }} /> : null}
      <Toast toast={toast} />
    </View>
  );
}

AppRegistry.registerComponent('lz4-compression', () => App);
