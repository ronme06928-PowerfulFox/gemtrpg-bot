(function () {
  window.createDrillCalculation = ({request,onResult,onError,onPending,delay=350}) => {
    let token=0, timer, abort, destroyed=false;
    return {
      schedule(body) {
        const current=++token;
        clearTimeout(timer); abort?.abort();
        if (destroyed) return;
        onPending();
        timer=setTimeout(async () => {
          abort=new AbortController();
          try {
            const result=await request(body,abort.signal);
            if (!destroyed && current === token) onResult(result);
          } catch (error) {
            if (!destroyed && current === token && error.name !== 'AbortError') onError(error);
          }
        },delay);
      },
      cancel() { ++token; clearTimeout(timer); abort?.abort(); },
      destroy() { destroyed=true; this.cancel(); },
    };
  };
})();
