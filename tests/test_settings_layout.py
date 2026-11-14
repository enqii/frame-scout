"""The AI settings of the tab "Settings" in two groups (F32), read from the app's source (CI has no streamlit)."""
import ast

from app_source import UI_PACKAGE
from framescout_core import AI_DETAIL_SETTINGS, AI_SETTINGS, PERSON_DETECTION_SETTINGS

SETTINGS_UI = UI_PACKAGE / 'settings.py'
DETAILS_LABEL = 'Person detection and reference images'


def show_ai_settings():
    tree = ast.parse(SETTINGS_UI.read_text(encoding='utf-8'), str(SETTINGS_UI))
    [function] = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'show_ai_settings']
    return function


def setting_widgets():
    """{setting name: (widget call, the st.expander labels around it)} of show_ai_settings."""
    widgets = {}

    def visit(node, expanders):
        if isinstance(node, ast.With):
            context = node.items[0].context_expr
            if isinstance(context, ast.Call) and ast.unparse(context.func) == 'st.expander':
                expanders = (*expanders, ast.unparse(context.args[0]))
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                value = keyword.value
                if (keyword.arg == 'key' and isinstance(value, ast.Call) and ast.unparse(value.func) == 'setting_key'
                        and isinstance(value.args[0], ast.Constant)):
                    widgets[value.args[0].value] = (node, expanders)
        for child in ast.iter_child_nodes(node):
            visit(child, expanders)

    visit(show_ai_settings(), ())
    return widgets


def test_the_groups_split_the_ai_settings_with_the_everyday_ones_first():
    everyday = AI_SETTINGS[:len(AI_SETTINGS) - len(AI_DETAIL_SETTINGS)]
    assert everyday == ('model', 'device', 'batch_size', 'low_priority', 'top')
    assert AI_SETTINGS[len(everyday):] == AI_DETAIL_SETTINGS
    assert AI_DETAIL_SETTINGS == ('person_detection', 'max_persons', 'person_confidence', 'reference_weight')
    assert PERSON_DETECTION_SETTINGS == ('max_persons', 'person_confidence')


def test_every_ai_setting_has_one_widget_in_its_group():
    widgets = setting_widgets()
    assert set(widgets) == set(AI_SETTINGS)
    for name in AI_SETTINGS:
        expanders = widgets[name][1]
        if name in AI_DETAIL_SETTINGS:
            assert expanders == ("'Person detection and reference images'",), name
        else:
            assert expanders == (), name


def details_expander():
    expanders = [node.items[0].context_expr for node in ast.walk(show_ai_settings()) if isinstance(node, ast.With)
                 and ast.unparse(node.items[0].context_expr).startswith(f'st.expander({DETAILS_LABEL!r}')]
    assert len(expanders) == 1, expanders
    return expanders[0]


def test_the_expander_does_not_close_by_itself_while_the_user_edits():
    # Streamlit closes an open expander when `expanded` turns False on a rerun, e.g. after a
    # value is set back to its default (review): `expanded` only ever turns True in a session
    [expanded] = [keyword.value for keyword in details_expander().keywords if keyword.arg == 'expanded']
    assert ast.unparse(expanded) == "st.session_state.get('ai_details_open', False)"
    function = show_ai_settings()
    opens = [node for node in ast.walk(function) if isinstance(node, ast.Assign)
             and [ast.unparse(target) for target in node.targets] == ["st.session_state['ai_details_open']"]]
    assert len(opens) == 1, f'one place opens the expander, found {len(opens)}'
    assert ast.unparse(opens[0].value) == 'True'
    openings = [node for node in ast.walk(function) if isinstance(node, ast.If) and opens[0] in node.body]
    assert len(openings) == 1, 'the expander is opened only under a condition'
    opening = openings[0]
    assert ast.unparse(opening.test).startswith('changed_from_defaults(')
    assert 'AI_DETAIL_SETTINGS' in ast.unparse(opening.test)
    assert opening.lineno < details_expander().lineno


def test_the_widgets_are_drawn_in_the_order_of_the_settings():
    widgets = setting_widgets()
    lines = [widgets[name][0].lineno for name in AI_SETTINGS]
    assert lines == sorted(lines)


def disabled_of(name):
    [disabled] = [keyword.value for keyword in setting_widgets()[name][0].keywords if keyword.arg == 'disabled']
    return ast.unparse(disabled)


def test_the_person_settings_are_disabled_while_the_detection_is_off():
    for name in PERSON_DETECTION_SETTINGS:
        assert disabled_of(name) == 'active or not detecting', name
    # the detection's own checkbox value of this page run, after the settings were synchronized
    [assign] = [node for node in ast.walk(show_ai_settings()) if isinstance(node, ast.Assign)
                and [ast.unparse(target) for target in node.targets] == ['detecting']]
    assert ast.unparse(assign.value) == "st.session_state[setting_key('person_detection')]"
    detection_line = setting_widgets()['person_detection'][0].lineno
    assert detection_line < assign.lineno < setting_widgets()['max_persons'][0].lineno
    # the other settings only while a run is active
    for name in set(AI_SETTINGS) - set(PERSON_DETECTION_SETTINGS):
        assert disabled_of(name) == 'active', name


def test_the_widgets_get_their_values_only_through_the_session_state():
    # CLAUDE.md gotcha (PR #10 review): never value= or index=
    for name, (call, _) in setting_widgets().items():
        assert not {keyword.arg for keyword in call.keywords} & {'value', 'index'}, name
