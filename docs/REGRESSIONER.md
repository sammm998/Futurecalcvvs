# Regressionerna som uppdraget namnger, och var de hålls

Uppdraget namnger de fall läsningen aldrig får tappa igen. Den ursprungliga numrerade listan följde inte med
sammanhanget när det byttes; sviten här är byggd ur de ämnen uppdraget namnger, ett prov per ämne, och varje
prov ritar ett litet blad där felet skulle synas som ett tal. `python3 -m pytest -q engine/tests` kör alla.

| # | Ämne | Prov |
|--:|---|---|
| 1 | Råkontakt är ingen anslutning: en linje som passerar tar inte namnet | `test_a_crossing_is_not_a_connection.py` |
| 2 | T-kandidat kräver positivt bevis; en gren i tomma luften är en fråga, inte ett svar | `test_a_branch_needs_evidence_to_take_a_name.py`, `test_boundary_rules.py::test_an_unlabeled_branch_takes_the_only_junction_identity_only_with_evidence_at_its_end` |
| 3 | Huvudstråkets kontinuitet bevaras när grenen avvisas | `test_a_branch_needs_evidence_to_take_a_name.py::test_a_branch_that_ends_in_empty_air_is_a_question_not_an_answer` |
| 4 | Flödesbudgeten är stråkets egen, inte pennans | `test_a_branch_needs_evidence_to_take_a_name.py::test_the_flow_budget_is_the_runs_own_not_the_pens` |
| 5 | Inget rör slutar tyst: varje kant har ett skäl | `test_no_pipe_ends_silently.py` |
| 6 | Fragmenteringsgrammatik ur bladet: streck, punkt, gap-mod, hörn | `test_a_dash_dot_line_is_one_run.py`, `test_grammar_leaders_pipes.py`, `test_a_layer_name_does_not_reach_across_a_gap.py` |
| 7 | En ventil i linjen avslutar inte röret | `test_a_valve_in_the_line_does_not_end_the_pipe.py` |
| 8 | Samlarlinjen bär hänvisningen till röret | `test_a_collector_line_carries_the_leader_to_the_pipe.py` |
| 9 | Parad vägg: två långsidor är ett föremål, inte två rör | `test_a_pipe_drawn_as_two_lines_is_one_pipe.py`, `test_two_pipes_side_by_side_are_two_pipes.py` |
| 10 | Skrafferad radiator är inte rör; rör i vägg ligger utanför den horisontella mängden | `test_a_hatched_radiator_is_not_a_pipe.py`, `test_regressions_named_in_the_mandate.py::test_pipe_in_a_hatched_wall_is_outside_the_horizontal_quantity_unless_asked_for` |
| 11 | Dubbletter: en linje ritad två gånger är ett rör | `test_regressions_named_in_the_mandate.py::test_a_line_the_export_drew_twice_is_one_pipe`, `test_declined.py` |
| 12 | Kurvor mäts längs bågen | `test_regressions_named_in_the_mandate.py::test_a_curved_run_is_measured_along_its_arc` |
| 13 | Hänvisning är aldrig "närmast" | `test_regressions_named_in_the_mandate.py::test_a_leader_that_reaches_no_pipe_is_never_given_the_nearest_one`, `test_leader_claims.py`, `test_claimed_runs.py` |
| 14 | En förbindelse mellan två dimensioner förblir tvetydig | `test_a_connector_between_two_sizes_stays_ambiguous.py`, `test_bundle_elimination.py` |
| 15 | En penna som ritar både hänvisningar och rör | `test_pen_shared_by_leaders_and_pipes.py`, `test_single_pen_sheet.py` |
| 16 | Legenden är inte obligatorisk, men avgör vad som är rör när den finns | `test_the_legend_decides_what_names_a_pipe.py`, `test_set_legend.py`, `test_a_material_class_bridges_the_legend_and_the_book.py` |
| 17 | Bladets tabell deklarerar anslutningsrör | `test_a_sheet_table_names_the_connection_pipes.py` |
| 18 | Skala: enhet på skalstocken, osäker skala är aldrig en säker meter, lånad skala från handlingen | `test_the_scale_bar_keeps_its_unit.py`, `test_an_unsettled_scale_is_not_a_confirmed_metre.py`, `test_handling.py` |
| 19 | Vertikalt är UNKNOWN utan bevis; en vågrät etikett är ingen stigare | `test_a_horizontal_label_is_not_a_riser.py`, `test_grammar_leaders_pipes.py` |
| 20 | Påskrift är inte ritning: inventering före klassificering, borttagning med bevis | `test_marks_are_inventoried_before_the_page_is_classified.py`, `test_markup_is_not_drawing.py` |
| 21 | Bläckkontraktet: fylld form utan penna är ingen linje | `test_fill_and_stroke_is_one_contract.py` |
| 22 | Determinism (original / omvänd / slumpad ordning), konservering, kontaminationsbrandvägg | `test_system.py`, `test_rules.py` |
| 23 | Andra läsaren och synen är bundna till kandidater och flyttar aldrig en meter | `test_astra.py`, `test_vision.py`, `test_judge.py`, `test_agent_edits.py` |
| 24 | Exporter bär vertikalt UNKNOWN; servern mäter, aldrig webbläsaren; regelverket rör bara anbudet | `test_api.py`, `test_the_measurement_engine.py`, `test_the_cad_room_draws_a_sheet.py` |
| 25 | Titelrutans brus, bildberoenden, indata-klassning | `test_titleblock_noise.py`, `test_image_dependencies.py`, `test_input_classification.py` |

Det som saknas prov för därför att det saknas i motorn (SYSTEM_AUDIT): skala per region på samma blad,
ritningslokala underfamiljer på en penna, adaptiv Bézier-plattning (n=8 fast; bågprovet ovan håller 2 %).
