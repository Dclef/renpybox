/** Agent 助手页：展示当前项目和服务可用状态。 */

import type { AppState } from '../useAppState';
import { IconRobot } from '../icons';

export function AgentPage(props: { state: AppState }) {
  const { state } = props;
  const projectPath = String(state.project?.renpy_project_path ?? '');
  const projectName = projectPath.split(/[\\/]/).pop() || '未选择项目';

  return (
    <div className="agent-workspace">
      <header className="agent-topbar">
        <span className="agent-avatar" aria-hidden="true">
          <IconRobot size={19} />
        </span>
        <div className="agent-heading">
          <h1 className="agent-title">Agent 助手</h1>
          <span className="agent-project-text" title={projectPath}>当前项目：{projectName}</span>
        </div>
      </header>

      <section className="agent-chat" aria-label="Agent 助手状态">
        <div className="agent-empty">
          <span className="agent-empty-icon" aria-hidden="true">
            <IconRobot size={30} />
          </span>
          <h2>Agent 助手暂不可用</h2>
          <p>自然语言编排服务尚未接入。</p>
        </div>
      </section>
    </div>
  );
}
