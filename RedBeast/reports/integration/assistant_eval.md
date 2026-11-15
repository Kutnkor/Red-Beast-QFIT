# Live QFIT evaluation

User-supplied OpenAI credential used only on the local server. Model: gpt-5.4-mini, reasoning none. No credential values appear in this report.

Ten questions (two for each target) completed with source links and no tool errors. The numeric grounding checker flagged no unsupported numbers; that checker does **not** detect all semantic mistakes. Manual review found one substantive RW Aur source/adoption distinction error and an omitted R Dra uncertainty. The prompt was strengthened and two real-provider follow-ups corrected those cases. This is a small model sample, not a guarantee of accuracy or scientific validity.

| Target | What is visible? | Where do the numbers come from? | Review |
|---|---|---|---|
| Barnard | Representative surface/corona/wind identified | Profile vs Gaia temperature distinguished; ± values reported | Source-backed in sample |
| Epsilon Indi B | Separate schematic binary/clouds, unresolved by SPHEREx | No adopted radius or single system temperature; component model values | Source-backed in sample |
| WISE 0855 | Representative visible appearance/cloud map | Approximate model temperature, unknown radius | Source-backed in sample |
| RW Aur | Disk/jets are schematic geometry based on source context | Initial answer confused adopted/derived and shared source | Corrected in live follow-up; retain caveat on model reliability |
| R Dra | Historical, phase-specific values and representative outflow | Historic radius/temperature with uncertainties | Incidental uncertainty omission corrected in follow-up |

## Follow-up responses

### rw-aur

Gösterilen sıcaklık ve yarıçapın kaynağı, RW Aurigae için projeye yüklenmiş yıldız profili kaydıdır; sıcaklık 4870 K olarak Gangi et al. (2022) Tablo 2’de RW Aur A satırından alınmış benimsenmiş bir tayfsal parametredir, yarıçap ise aynı kaynak kümesinde etkin sıcaklık ve ışıma gücünden hesaplanmış türetilmiş bir değerdir. Bu nedenle her ikisi de rastgele çizim değil, kaynaklı ve etiketli profile değerleridir; ancak yarıçap için verilen hata çubuğu hedefe özel bir ölçüm değil, örneklem düzeyinde yaklaşık 0,3 dex belirsizlik notudur. [K1]

Özetle: sıcaklık “measured/adopted” olarak işaretli, yarıçap ise “computed” yani benimsenmiş ama hesaplanmış değerdir; ikisi de aynı kaynak kimliği `rw-stellar` ile ilişkilidir, dolayısıyla farklı kaynaklardan gelmiyorlar. Belirsizlik tarafında sıcaklık satırında tek tek bir ± değer verilmemiştir; yarıçap için de 1.8 R☉ yanında açık bir sayısal ± yazmıyor, yalnızca yaklaşık 0,3 dex’lik örneklem belirsizliği belirtiliyor. [K1]

### r-dra

Yüzeyde gördüğünüz şey gerçek bir teleskop yüzey haritası değil; R Draconis için çizilmiş temsili bir Mira-vari kırmızı dev görünümü. Kaynak profilde bu yıldızın nabız atan bir Mira olduğu, yüzey desenleri ile renk/kontrast değişiminin gösterimde şematik tutulduğu ve sıcaklık ile yarıçapın tarihsel, faza özgü ve modele bağlı olduğu belirtiliyor [K1].

Çevresinde görülen yapı da temsili bir tozlu rüzgâr zarfı: pulsasyonla desteklenen toz çıkışı Mira sınıfı için bir şablon olarak açılmış, ama R Dra için kütle kaybı oranı, rüzgâr hızı ya da toz yoğunluğu benimsenmemiş [K1]. Sayı olarak yalnızca tarihsel bir örnek verilebiliyor: 511 ± 142 R☉ ve 2034 ± 139 K; bunlar güncel fotosfer ölçümü değil, 1997-07-05 tarihli faza özgü türetilmiş değerlerdir [K1].

## Boundaries

Only local knowledge retrieval and manual UI proposals are available. This evaluation did not independently re-verify the astronomical literature or live archive availability. No surface graphic is represented as a telescope photograph. Offline adapter/maskot tests are reported separately. The distributed ZIP remains key-free and AI-off by default.

## Live UI proposal round trip

The final local HTTP route returned `text → command → sources → done` from the real provider. `propose_ui_command` emitted `set_year` with year 2050. The browser did not execute it during the test. Fixture-based component tests separately verify that a user click is required.
