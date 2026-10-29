import { checkJob } from "@/app/actions";

export async function POST(request: Request): Promise<Response> {
	const input = await request.json().catch(() => null);
	const result = await checkJob(input);

	return Response.json(result, {
		headers: {
			"Cache-Control": "no-store",
		},
	});
}
