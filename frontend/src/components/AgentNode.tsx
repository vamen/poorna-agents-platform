import { memo } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { cn } from '../lib/utils'

export const AgentNode = memo(({ data, selected }: NodeProps) => {
  const isLongRunning = (data as any).isLongRunning as boolean | undefined

  return (
    <div
      className={cn(
        'rounded-lg border-2 px-4 py-3 shadow-md min-w-[160px] cursor-pointer transition-all',
        isLongRunning
          ? 'bg-violet-50 border-violet-400 text-violet-900'
          : 'bg-sky-50 border-sky-400 text-sky-900',
        selected && 'ring-2 ring-offset-2 ring-blue-500'
      )}
    >
      <Handle type="target" position={Position.Left} className="w-3 h-3 !bg-gray-400" />
      <div className="font-semibold text-sm">{data.label as string}</div>
      {data.agentType && (
        <div className="text-xs opacity-60 mt-0.5">{data.agentType as string}</div>
      )}
      {data.agentName && (
        <div className="text-xs opacity-75 mt-1 truncate max-w-[140px]">{data.agentName as string}</div>
      )}
      {isLongRunning && (
        <div className="text-xs mt-1 opacity-50 italic">long-running</div>
      )}
      <Handle type="source" position={Position.Right} className="w-3 h-3 !bg-gray-400" />
    </div>
  )
})

AgentNode.displayName = 'AgentNode'
