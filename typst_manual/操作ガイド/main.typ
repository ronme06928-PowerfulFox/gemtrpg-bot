// セッション操作ガイド（計画46・4D〜4Fで制作中）
// Build: typst compile --root typst_manual typst_manual/操作ガイド/main.typ output/pdf/46_operation_guide.pdf
#import "../manual_theme.typ": guide-conf, guide-cover, publication-toc

#import "../publication_info.typ": publications, publication-status
#set document(title: "ジェムリアTRPG " + publications.guide.title + "・" + publications.guide.edition)
#show: guide-conf

#guide-cover()
#publication-toc(guide: true)

#include "00_この本の使い方.typ"
#include "01_始める前に.typ"
#include "02_キャラクターを用意する.typ"
#include "03_画面を読む.typ"
#include "04_探索と戦闘を操作する.typ"
#include "05_セッションの後.typ"
#include "06_GM_卓を準備する.typ"
#include "07_GM_当日を進める.typ"
#include "08_GM_介入と復旧.typ"
#include "09_GM_素材を作る.typ"
#include "90_困ったときの索引.typ"

#import "../publication_endmatter.typ": publication-endmatter
#publication-endmatter("guide")
