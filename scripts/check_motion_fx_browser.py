"""PR4.5b: real browser checks for reversible reactions in generated previews."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_local/pr45b_check"


def seek(page, value, scope=""):
    return page.locator(f"{scope} .seek".strip()).evaluate(
        "(el,t)=>{el.value=String(t);el.dispatchEvent(new Event('input'));}", value)


def choose(locator, value):
    locator.evaluate("(el,v)=>{el.value=v;el.dispatchEvent(new Event('change'));}", value)


def main():
    checks = 0
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", timeout=15000)
        page = browser.new_page(viewport={"width": 1440, "height": 1080})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("https://**", lambda route: route.abort())
        page.goto((ROOT / "_local/fx_gallery/fx_gallery.html").as_uri(), wait_until="domcontentloaded")
        assert page.locator(".gallery-card").count() == 23
        for effect in ["attack-slash", "attack-strike", "attack-pierce", "hit-react", "hit-shake"]:
            card = f'.effect-card[data-effect="{effect}"]'
            options = page.locator(card + " .sample option").evaluate_all("els=>els.map(el=>el.value)")
            # 全パラメータの組はNodeテストで覆い、実DOMでは両端の代表を検査する。
            options = [options[0], options[-1]]
            for option in options:
                choose(page.locator(card + " .sample"), option)
                for strength in ["light", "normal", "rich"]:
                    choose(page.locator(card + " .level"), strength)
                    for t in ([0.04, 0.15, 0.3] if effect.startswith("hit-") else [0.69, 0.7, 0.75, 0.78, 1.08]):
                        seek(page, t, card)
                        shot = page.locator(card + " .stage-host").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))")
                        seek(page, 0, card)
                        seek(page, t, card)
                        assert page.locator(card + " .stage-host").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))") == shot, (effect, option, strength, t)
                        checks += 1
                    seek(page, 0.04, card)
                    changed = page.locator(card + " .stage-host [data-anchor]").evaluate_all(
                        "els=>els.filter(el=>el.style.translate && el.style.translate!=='none').length")
                    if effect.startswith("hit-"):
                        assert bool(changed) == (strength != "light" and not (effect == "hit-shake" and "small" in option)), (effect, option, strength, changed)
                    seek(page, 1.4, card)
                    assert not page.locator(card + " .stage-host [data-anchor]").evaluate_all("els=>els.some(el=>el.style.translate)")
            print(effect, checks, flush=True)
        print("gallery checks", checks, flush=True)
        page.goto((ROOT / "_local/resolve_preview/resolve_preview.html").as_uri(), wait_until="domcontentloaded")
        for width in ["1180", "660"]:
            choose(page.locator(".width-select"), width)
            for sample in ["ally-win", "enemy-ko", "one-sided", "summation", "fizzle", "hard-attack", "mass-individual"]:
                choose(page.locator(".sample-select"), sample)
                for level in ["light", "normal", "rich"]:
                    choose(page.locator(".level-select"), level)
                    for t in [2.4, 2.44, 2.52, 2.6, 2.8, 0]:
                        seek(page, t)
                        shot = page.locator(".preview-canvas").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))")
                        seek(page, 4.5)
                        seek(page, t)
                        assert page.locator(".preview-canvas").evaluate("el=>JSON.stringify([...el.querySelectorAll('*')].map(n=>[n.getAttribute('class'),n.style.cssText,n.getAttribute('transform'),n.getAttribute('d'),n.children.length?null:n.textContent]))") == shot, (sample, level, t)
                        checks += 1
                    if sample == "summation" and level != "light":
                        seek(page, 2.44)
                        assert page.locator(".participants .portrait").evaluate_all("els=>els.every(el=>!!el.style.translate)")
                        seek(page, 2.52)
                        data = page.evaluate("""() => {
                          const lane=document.querySelector('[data-anchor="damage:participants"]');
                          const group=document.querySelector('.participants');
                          const attack=document.querySelector('.event-attack-slash,.event-attack-strike,.event-attack-pierce,.event-attack-flash');
                          const numbers=[...lane.querySelectorAll('.fx-root')];
                          return {lane:lane.style.translate,group:group.style.translate,attack:attack.style.translate,
                            inBounds:numbers.every(el=>parseFloat(el.style.left)>0&&parseFloat(el.style.left)<parseFloat(lane.style.width))};
                        }""")
                        assert data["lane"] and data["lane"] == data["group"] == data["attack"], data
                        assert data["inBounds"], data
        choose(page.locator(".sample-select"), "summation")
        choose(page.locator(".width-select"), "1180")
        choose(page.locator(".level-select"), "rich")
        seek(page, 2.52)
        OUT.mkdir(parents=True, exist_ok=True)
        page.locator(".preview-view").screenshot(path=str(OUT / "latest.png"))
        assert not errors, errors
        browser.close()
    print(json.dumps({"browser_checks": checks, "page_errors": errors}))


if __name__ == "__main__":
    main()
